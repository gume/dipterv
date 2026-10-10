#!/usr/bin/env python3

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import pymupdf
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from create_db import ensure_extract_schema


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = "/db/descriptions.sqlite"
DEFAULT_DATA_DIR = "/data"
DEFAULT_TEMPLATES_DIR = APP_DIR / "templates"


class VisualElement(BaseModel):
	element_type: str = Field(description="One visual element identifier from the selected template")
	is_present: bool = Field(description="True when this element is present in its expected area")
	box_2d: list[int] | None = Field(
		default=None,
		description="[ymin, xmin, ymax, xmax] normalized to the 0-1000 scale",
	)


class ThesisAssignmentSchema(BaseModel):
	detected_template: str
	template_valid: bool
	missing_boilerplate_rules: list[str]
	layout_discrepancies: list[str]
	header_dept_head: str | None = Field(default=None, description="Exact matched header department-head boilerplate, or null")
	thesis_type: str | None = Field(default=None, description="Exact matched thesis-type boilerplate, or null")
	student_suffix: str | None = Field(default=None, description="Exact matched student suffix boilerplate, or null")
	task_intro: str | None = Field(default=None, description="Exact matched task-introduction boilerplate, or null")
	supervisor_label: str | None = Field(default=None, description="Exact matched supervisor-label boilerplate, or null")
	dept_head_title: str | None = Field(default=None, description="Exact matched department-head title boilerplate, or null")
	footer_university: str | None = Field(default=None, description="Exact matched university-footer boilerplate, or null")
	footer_faculty: str | None = Field(default=None, description="Exact matched faculty-footer boilerplate, or null")
	footer_department: str | None = Field(default=None, description="Exact matched department-footer boilerplate, or null")
	student_name: str
	student_status: str
	thesis_title: str
	problem_background: str
	project_goal: str
	tasks: list[str]
	supervisor: str
	cosupervisor: str | None = None
	department_head: str
	issue_date: str
	visual_elements: list[VisualElement]


def positive_int(value):
	try:
		parsed = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("must be an integer") from exc
	if parsed <= 0:
		raise argparse.ArgumentTypeError("must be greater than zero")
	return parsed


def nonnegative_int(value):
	try:
		parsed = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("must be an integer") from exc
	if parsed < 0:
		raise argparse.ArgumentTypeError("must be zero or greater")
	return parsed


def parse_args(argv=None):
	parser = argparse.ArgumentParser(
		description="Extract thesis-assignment fields from PDFs listed in the import table."
	)
	parser.add_argument(
		"--database",
		default=DEFAULT_DATABASE,
		help=f"SQLite database path (default: {DEFAULT_DATABASE})",
	)
	parser.add_argument(
		"--data-dir",
		default=DEFAULT_DATA_DIR,
		help=f"Directory containing imported PDFs (default: {DEFAULT_DATA_DIR})",
	)
	parser.add_argument(
		"--templates-dir",
		default=str(DEFAULT_TEMPLATES_DIR),
		help="Directory containing language template JSON files.",
	)
	parser.add_argument(
		"--model",
		default="gemini-3.5-flash-lite",
		help="Google GenAI model ID; model names containing 'gemma' use a first-page image.",
	)
	parser.add_argument(
		"--timeout",
		type=positive_int,
		default=60,
		help="Request timeout in seconds (default: 60).",
	)
	parser.add_argument(
		"--limit",
		type=nonnegative_int,
		default=None,
		help="Maximum number of pending PDF files to send for extraction; existing extract rows do not count.",
	)
	parser.add_argument(
		"--json",
		action="store_true",
		help="Print each successfully extracted result as JSON.",
	)
	return parser.parse_args(argv)


def load_templates(templates_dir):
	template_paths = sorted(glob.glob(os.path.join(templates_dir, "*.json")))
	if not template_paths:
		raise ValueError(f"No template JSON files found in '{templates_dir}'.")

	templates = {}
	for template_path in template_paths:
		with open(template_path, encoding="utf-8") as template_file:
			template = json.load(template_file)
		template_id = template.get("template_id", Path(template_path).stem)
		templates[template_id] = template
	return templates


def pending_filenames(connection):
	return [
		row[0]
		for row in connection.execute(
			"""
			SELECT i.filename
			FROM "import" AS i
			LEFT JOIN "extract" AS e ON e.filename = i.filename
			WHERE e.filename IS NULL
			ORDER BY i.row_id, i.filename
			"""
		)
	]


def pending_pdf_filenames(connection, data_dir, limit=None):
	if limit == 0:
		return []

	selected = []
	for filename in pending_filenames(connection):
		pdf_path = Path(data_dir) / filename
		if not pdf_path.is_file():
			print(f"WARNING: PDF not found for database record: {pdf_path}", file=sys.stderr)
			continue
		selected.append(filename)
		if limit is not None and len(selected) >= limit:
			break
	return selected


def build_prompt(templates):
	return f"""You are an academic thesis-assignment document auditor.
Analyze the supplied PDF and return all fields in the requested JSON schema.

AVAILABLE LANGUAGE TEMPLATES:
{json.dumps(templates, ensure_ascii=False, indent=2)}

Instructions:
1. Detect the document language and choose the matching template_id.
2. For every required_boilerplate rule in that template, match any one variant and put the exact matched text in the output field whose name is that rule's rule_id. Use null when no variant matches. Also list unmatched rule_ids in missing_boilerplate_rules.
3. Check the expected layout and report any discrepancies.
4. Extract the student name/status, thesis title, background, goal, task list, supervisor(s), department head, and issue date. Use an empty string for unavailable text; use null only for the optional cosupervisor.
5. For each visual_elements_to_detect item in the selected template, return its element_type, whether it is present in the expected area, and its box_2d [ymin, xmin, ymax, xmax] normalized to 0-1000. Use null for box_2d when unavailable. Do not crop, encode, return, or save image data.
6. Set template_valid to true only when the required boilerplate and layout requirements are satisfied.
"""


def make_pdf_part(pdf_path, model):
	if "gemma" in model.lower():
		with pymupdf.open(pdf_path) as document:
			page = document[0]
			image_bytes = page.get_pixmap(dpi=200).tobytes("png")
		return types.Part.from_bytes(data=image_bytes, mime_type="image/png")

	return types.Part.from_bytes(
		data=Path(pdf_path).read_bytes(), mime_type="application/pdf"
	)


def is_resource_exhausted_429(error):
	message = " ".join(
		str(value)
		for value in (error, getattr(error, "message", ""), getattr(error, "status", ""))
	).upper()
	code = getattr(error, "code", None) or getattr(error, "status_code", None)
	return "RESOURCE_EXHAUSTED" in message and (code == 429 or "429" in message)


def extract_pdf(client, pdf_path, model, prompt):
	pdf_part = make_pdf_part(pdf_path, model)
	request = {
		"model": model,
		"contents": [pdf_part, prompt],
		"config": types.GenerateContentConfig(
			temperature=0.0,
			response_mime_type="application/json",
			response_schema=ThesisAssignmentSchema,
		),
	}
	try:
		response = client.models.generate_content(**request)
	except Exception as error:
		if not is_resource_exhausted_429(error):
			raise
		print("LLM rate limit exhausted (429); retrying once in 60 seconds.", file=sys.stderr)
		time.sleep(60)
		response = client.models.generate_content(**request)
	raw_text = (response.text or "").strip()
	if raw_text.startswith("```"):
		raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
		raw_text = re.sub(r"\s*```$", "", raw_text)
	if not raw_text:
		raise ValueError("Model returned an empty response.")
	return ThesisAssignmentSchema.model_validate_json(raw_text)


def result_database_values(result):
	visual_elements = {
		element.element_type: element
		for element in result.visual_elements
	}
	return {
		"valid": int(result.template_valid),
		"detected_template": result.detected_template,
		"header_dept_head": result.header_dept_head,
		"thesis_type": result.thesis_type,
		"student_suffix": result.student_suffix,
		"task_intro": result.task_intro,
		"supervisor_label": result.supervisor_label,
		"dept_head_title": result.dept_head_title,
		"footer_university": result.footer_university,
		"footer_faculty": result.footer_faculty,
		"footer_department": result.footer_department,
		"missing_boilerplate_rules_json": json.dumps(
			result.missing_boilerplate_rules, ensure_ascii=False
		),
		"layout_discrepancies_json": json.dumps(
			result.layout_discrepancies, ensure_ascii=False
		),
		"student_name": result.student_name,
		"student_status": result.student_status,
		"thesis_title": result.thesis_title,
		"problem_background": result.problem_background,
		"project_goal": result.project_goal,
		"tasks_json": json.dumps(result.tasks, ensure_ascii=False),
		"supervisor": result.supervisor,
		"cosupervisor": result.cosupervisor,
		"department_head": result.department_head,
		"issue_date": result.issue_date,
		"university_logo_present": int(visual_elements["university_logo"].is_present) if "university_logo" in visual_elements else None,
		"university_logo_box_2d_json": json.dumps(visual_elements["university_logo"].box_2d) if visual_elements.get("university_logo") and visual_elements["university_logo"].box_2d else None,
		"department_logo_present": int(visual_elements["department_logo"].is_present) if "department_logo" in visual_elements else None,
		"department_logo_box_2d_json": json.dumps(visual_elements["department_logo"].box_2d) if visual_elements.get("department_logo") and visual_elements["department_logo"].box_2d else None,
		"signature_space_present": int(visual_elements["signature_space"].is_present) if "signature_space" in visual_elements else None,
		"signature_space_box_2d_json": json.dumps(visual_elements["signature_space"].box_2d) if visual_elements.get("signature_space") and visual_elements["signature_space"].box_2d else None,
	}


def store_result(connection, filename, values):
	columns = ("filename", *values)
	placeholders = ", ".join("?" for _ in columns)
	column_list = ", ".join(f'"{column}"' for column in columns)
	connection.execute(
		f'INSERT INTO "extract" ({column_list}) VALUES ({placeholders})',
		(filename, *values.values()),
	)
	connection.commit()


def main(argv=None):
	args = parse_args(argv)
	templates = load_templates(args.templates_dir)
	prompt = build_prompt(templates)

	connection = sqlite3.connect(args.database)
	ensure_extract_schema(connection)
	files = pending_pdf_filenames(connection, args.data_dir, args.limit)
	if not files:
		print("No files need extraction.")
		connection.close()
		return 0

	client = genai.Client(
		http_options=types.HttpOptions(timeout=args.timeout * 1000)
	)
	processed = 0
	saved = 0
	failures = 0
	for filename in files:
		pdf_path = Path(args.data_dir) / filename
		processed += 1
		print(f"[{processed}{f'/{args.limit}' if args.limit is not None else ''}] Extracting {filename}")
		try:
			result = extract_pdf(client, str(pdf_path), args.model, prompt)
			store_result(connection, filename, result_database_values(result))
		except Exception as error:
			failures += 1
			print(f"ERROR: Extraction failed for {filename}: {error}", file=sys.stderr)
			continue

		saved += 1
		if args.json:
			print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
		else:
			print(
				f"Stored {filename}: template={result.detected_template}, "
				f"valid={result.template_valid}, "
				f"missing_boilerplate={len(result.missing_boilerplate_rules)}"
			)

	connection.close()
	print(f"Extraction finished: processed {processed}, stored {saved}, failed {failures}.")
	return 1 if failures else 0


if __name__ == "__main__":
	raise SystemExit(main())
