#!/usr/bin/env python3

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import tomllib
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from create_db import ensure_schema


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = APP_DIR / "review_config.toml"


class AspectResult(BaseModel):
	key: str
	score: int
	reasoning: str


class ReviewSchema(BaseModel):
	results: list[AspectResult]


class SummarySchema(BaseModel):
	summary: str


def positive_int(value):
	try:
		parsed = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("must be an integer") from exc
	if parsed <= 0:
		raise argparse.ArgumentTypeError("must be greater than zero")
	return parsed


def parse_args(argv=None):
	parser = argparse.ArgumentParser(
		description="AI review of extracted thesis descriptions stored in the database."
	)
	parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="TOML configuration file.")
	parser.add_argument("--limit", type=positive_int, default=None, help="Maximum number of descriptions to review.")
	parser.add_argument("--model", default=None, help="Model ID; also used as the reviewer id.")
	parser.add_argument(
		"--filename",
		default=None,
		help="Review only this import filename, replacing any existing review by the same reviewer.",
	)
	return parser.parse_args(argv)


def load_config(path):
	with open(path, "rb") as config_file:
		return tomllib.load(config_file)


def pending_documents(connection, reviewer, aspects, limit=None, filename=None):
	# Only extracted descriptions; rerun when this reviewer's configured aspects are incomplete.
	query = """
		SELECT i.neptun_code, i.version, i.filename, i.degree, i.faculty,
		       e.thesis_title, e.problem_background, e.project_goal, e.task_intro, e.tasks_json
		FROM "import" AS i
		JOIN "extract" AS e ON e.filename = i.filename
		WHERE e.thesis_title IS NOT NULL
	"""
	params = []
	if filename is not None:
		query += " AND i.filename = ?"
		params.append(filename)
	else:
		aspect_placeholders = ", ".join("?" for _ in aspects)
		query += f"""
			AND (
				SELECT COUNT(DISTINCT r.aspect) FROM reviews AS r
				WHERE r.neptun_code = i.neptun_code AND r.version = i.version
				  AND r.reviewer = ? AND r.aspect IN ({aspect_placeholders})
			) < ?
			OR EXISTS (
				SELECT 1 FROM reviews AS r
				WHERE r.neptun_code = i.neptun_code AND r.version = i.version
				  AND r.reviewer = ? AND r.aspect NOT IN ({aspect_placeholders})
			)
			OR NOT EXISTS (
				SELECT 1 FROM review_summaries AS s
				WHERE s.neptun_code = i.neptun_code AND s.version = i.version AND s.reviewer = ?
			)
		"""
		params.extend((reviewer, *aspects, len(aspects), reviewer, *aspects, reviewer))
	query += " ORDER BY i.row_id, i.filename"
	if limit is not None:
		query += " LIMIT ?"
		params.append(limit)
	return connection.execute(query, params).fetchall()


def document_body(row):
	try:
		tasks = json.loads(row["tasks_json"] or "[]")
	except json.JSONDecodeError:
		tasks = []
	parts = [
		row["thesis_title"],
		row["problem_background"],
		row["project_goal"],
		row["task_intro"],
		"\n".join(f"{number}. {task}" for number, task in enumerate(tasks, 1)),
	]
	return "\n\n".join(part for part in parts if part)


def build_prompt(config, row, body):
	aspects = "\n".join(f'- key "{a["key"]}": {a["prompt"]}' for a in config["review"]["aspects"])
	reasoning_language = config["review"].get("reasoning_language", "the language of the document")
	return (
		f"Thesis description of a {row['degree']} student ({row['faculty']}).\n"
		f"Write the reasoning in: {reasoning_language}.\n\n"
		f"Questions:\n{aspects}\n\n"
		"Return exactly one result per key with an integer score from 1 to 5 and concise, specific reasoning. "
		"Support each score with evidence from the supplied text; quote exact errors or ambiguous phrases where relevant. "
		"Do not invent problems or overlook definite defects.\n\n"
		f"Document text:\n<<<\n{body}\n>>>"
	)


def is_rate_limited(error):
	message = f"{error} {getattr(error, 'status', '')}".upper()
	return (
		"RESOURCE_EXHAUSTED" in message
		or "QUOTA EXCEEDED" in message
		or getattr(error, "code", None) == 429
	)


def retry_delay_seconds(error):
	message = str(error)
	match = re.search(r"\bretry\s+in\s+(\d+(?:\.\d+)?)\s*(?:s|sec(?:onds?)?)\b", message, re.IGNORECASE)
	return float(match.group(1)) if match else None


def request_structured(client, config, model, prompt, response_schema, system_instruction):
	llm = config["llm"]
	request = {
		"model": model,
		"contents": prompt,
		"config": types.GenerateContentConfig(
			system_instruction=system_instruction,
			temperature=llm.get("temperature", 0.0),
			response_mime_type="application/json",
			response_schema=response_schema,
		),
	}
	attempts = llm.get("retries", 2) + 1
	for attempt in range(1, attempts + 1):
		try:
			response = client.models.generate_content(**request)
			return response_schema.model_validate_json((response.text or "").strip())
		except Exception as error:
			if attempt == attempts:
				raise
			if is_rate_limited(error):
				delay = retry_delay_seconds(error)
				if delay is None:
					delay = 60
			else:
				delay = 2 ** attempt
			print(f"WARNING: attempt {attempt}/{attempts} failed ({error}); retrying in {delay}s.", file=sys.stderr)
			time.sleep(delay)


def request_review(client, config, model, prompt):
	return request_structured(
		client, config, model, prompt, ReviewSchema, config["review"]["system_prompt"]
	)


def validated_scores(config, review):
	by_key = {item.key: item for item in review.results}
	scores = []
	for aspect in config["review"]["aspects"]:
		item = by_key.get(aspect["key"])
		if item is None or not 1 <= item.score <= 5:
			raise ValueError(f"Missing or invalid score for aspect '{aspect['key']}'.")
		scores.append((aspect["key"], item.score, item.reasoning.strip()))
	return scores


def build_summary_prompt(config, scores, average_score):
	reasoning_language = config["review"].get("reasoning_language", "the language of the document")
	findings = "\n".join(
		f"- {aspect}: {score}/5. {reasoning}" for aspect, score, reasoning in scores
	)
	return (
		f"Write the summary in {reasoning_language}. The exact arithmetic mean is {average_score:.2f}/5; "
		"the application will prepend that value, so do not repeat or recalculate it.\n"
		"Write one very concise summary (no more than 32 words) that reflects this average and the most important "
		"strength or weakness. Do not imply that all aspects have the same quality; "
		"surface a serious low-scoring issue even when the average is high. Do not include numeric scores in the summary. "
		"Use only the findings below, with no generic filler.\n\n"
		f"Aspect findings:\n{findings}"
	)


def request_summary(client, config, model, scores):
	if not scores:
		raise ValueError("Cannot summarize a review with no aspect scores.")
	average_score = sum(score for _, score, _ in scores) / len(scores)
	result = request_structured(
		client,
		config,
		model,
		build_summary_prompt(config, scores, average_score),
		SummarySchema,
		"You write concise, evidence-based summaries of thesis-description reviews. Return only the requested JSON.",
	)
	summary = result.summary.strip()
	if not summary:
		raise ValueError("Model returned an empty review summary.")
	return average_score, f"Average {average_score:.2f}/5. {summary}"


def store_review(connection, row, reviewer, scores, average_score, summary):
	key = (row["neptun_code"], row["version"], reviewer)
	with connection:
		connection.execute(
			"DELETE FROM reviews WHERE neptun_code = ? AND version = ? AND reviewer = ?", key
		)
		connection.executemany(
			"INSERT INTO reviews (neptun_code, version, reviewer, aspect, result, score) "
			"VALUES (?, ?, ?, ?, ?, ?)",
			[(*key, aspect, reasoning, score) for aspect, score, reasoning in scores],
		)
		connection.execute(
			"INSERT OR REPLACE INTO review_summaries "
			"(neptun_code, version, reviewer, average_score, summary, updated_at) "
			"VALUES (?, ?, ?, ?, ?, datetime('now'))",
			(*key, average_score, summary),
		)


def main(argv=None):
	args = parse_args(argv)
	config = load_config(args.config)
	model = args.model or config["llm"]["model"]

	if not os.environ.get("GEMINI_API_KEY"):
		print("ERROR: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
		return 2

	connection = sqlite3.connect(config["database"]["path"])
	connection.row_factory = sqlite3.Row
	ensure_schema(connection)
	aspects = [aspect["key"] for aspect in config["review"]["aspects"]]
	rows = pending_documents(connection, model, aspects, args.limit, args.filename)
	if not rows:
		print("No descriptions need review.")
		connection.close()
		return 1 if args.filename else 0

	client = genai.Client(
		http_options=types.HttpOptions(timeout=config["llm"].get("timeout", 120) * 1000)
	)
	stored = failures = 0
	for number, row in enumerate(rows, 1):
		print(f"[{number}/{len(rows)}] Reviewing {row['filename']} with {model}")
		try:
			body = document_body(row)
			review = request_review(client, config, model, build_prompt(config, row, body))
			scores = validated_scores(config, review)
			average_score, summary = request_summary(client, config, model, scores)
			store_review(connection, row, model, scores, average_score, summary)
		except Exception as error:
			failures += 1
			print(f"ERROR: Review failed for {row['filename']}: {error}", file=sys.stderr)
			continue
		stored += 1
		print(
			f"Stored {row['filename']}: average={average_score:.2f}, "
			+ ", ".join(f"{key}={score}" for key, score, _ in scores)
		)

	connection.close()
	print(f"Review finished: processed {len(rows)}, stored {stored}, failed {failures}.")
	return 1 if failures else 0


if __name__ == "__main__":
	raise SystemExit(main())
