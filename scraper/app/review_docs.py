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
OPENAI_ENV_KEY = "OPENAI_API_KEY"
OPENAI_ENV_URL = "OPENAI_BASE_URL"


class OpenAIClient:
	"""Chat-completions transport for OpenAI-compatible servers; the rest of the pipeline is shared."""

	def __init__(self, api_key, base_url, timeout):
		from openai import OpenAI

		self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
		self._no_temperature = set()

	@staticmethod
	def _rejects_temperature(error):
		# Reasoning models answer 400 unsupported_value for any non-default temperature.
		param = getattr(error, "param", None) or (getattr(error, "body", None) or {}).get("param")
		return getattr(error, "status_code", None) == 400 and (
			param == "temperature" or "'temperature'" in str(error)
		)

	def generate_text(self, model, prompt, response_schema, system_instruction, temperature):
		# json_object mode is the widest-supported option, so the schema is given in the prompt.
		schema = json.dumps(response_schema.model_json_schema(), ensure_ascii=False)
		request = {
			"model": model,
			"response_format": {"type": "json_object"},
			"messages": [
				{
					"role": "system",
					"content": f"{system_instruction}\n\nReturn only one JSON object conforming to this JSON schema:\n{schema}",
				},
				{"role": "user", "content": prompt},
			],
		}
		if model not in self._no_temperature:
			request["temperature"] = temperature
		try:
			response = self._client.chat.completions.create(**request)
		except Exception as error:
			if "temperature" not in request or not self._rejects_temperature(error):
				raise
			print(f"NOTE: {model} does not accept temperature={temperature}; using its default.", file=sys.stderr)
			self._no_temperature.add(model)
			del request["temperature"]
			response = self._client.chat.completions.create(**request)
		text = (response.choices[0].message.content or "").strip()
		return re.sub(r"^```(?:json)?\s*|\s*```$", "", text)


class AspectResult(BaseModel):
	key: str
	score: int
	reasoning: str


class ReviewSchema(BaseModel):
	results: list[AspectResult]


class SummarySchema(BaseModel):
	summary: str


class DocumentReview(BaseModel):
	document: str
	results: list[AspectResult]


class BatchReviewSchema(BaseModel):
	documents: list[DocumentReview]


class DocumentSummary(BaseModel):
	document: str
	summary: str


class BatchSummarySchema(BaseModel):
	summaries: list[DocumentSummary]


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
		"--openai",
		action="store_true",
		help=f"Use an OpenAI-compatible API instead of Google; needs {OPENAI_ENV_KEY} and {OPENAI_ENV_URL}; the model is taken from --model or the config.",
	)
	parser.add_argument(
		"--filename",
		default=None,
		help="Review only this import filename, replacing any existing review by the same reviewer.",
	)
	parser.add_argument(
		"--summary-model",
		default=None,
		help="Model for the short summaries (same interface as --model); defaults to --model. Useful to spread API quota.",
	)
	parser.add_argument(
		"--batch",
		type=positive_int,
		default=None,
		metavar="N",
		help="Review N descriptions per request (each still judged strictly on its own); default 1.",
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
		or 429 in (getattr(error, "code", None), getattr(error, "status_code", None))
	)


def retry_delay_seconds(error):
	message = str(error)
	match = re.search(r"\bretry\s+in\s+(\d+(?:\.\d+)?)\s*(?:s|sec(?:onds?)?)\b", message, re.IGNORECASE)
	if match:
		return float(match.group(1))
	headers = getattr(getattr(error, "response", None), "headers", None)
	try:
		return float(headers["retry-after"]) if headers and "retry-after" in headers else None
	except (TypeError, ValueError):
		return None


def request_structured(client, config, model, prompt, response_schema, system_instruction):
	llm = config["llm"]
	temperature = llm.get("temperature", 0.0)
	request = {
		"model": model,
		"contents": prompt,
		"config": types.GenerateContentConfig(
			system_instruction=system_instruction,
			temperature=temperature,
			response_mime_type="application/json",
			response_schema=response_schema,
		),
	}
	attempts = llm.get("retries", 2) + 1
	for attempt in range(1, attempts + 1):
		try:
			if isinstance(client, OpenAIClient):
				text = client.generate_text(model, prompt, response_schema, system_instruction, temperature)
			else:
				text = client.models.generate_content(**request).text
			return response_schema.model_validate_json((text or "").strip())
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


def batch_ids(rows):
	return {f"D{number}": row for number, row in enumerate(rows, 1)}


def build_batch_prompt(config, rows_by_id):
	aspects = "\n".join(f'- key "{a["key"]}": {a["prompt"]}' for a in config["review"]["aspects"])
	reasoning_language = config["review"].get("reasoning_language", "the language of the document")
	documents = "\n\n".join(
		f"=== DOCUMENT {doc_id} === ({row['degree']} student, {row['faculty']})\n<<<\n{document_body(row)}\n>>>"
		for doc_id, row in rows_by_id.items()
	)
	return (
		f"Below are {len(rows_by_id)} unrelated thesis descriptions. Treat every document as a completely separate, "
		"individual review: judge each one only on its own text and degree level, with exactly the same rigor and "
		"standards for all of them. Never compare documents, never let one document influence another's scores, and "
		"do not relax or tighten the criteria because of the number or quality of the other documents.\n"
		f"Write the reasoning in: {reasoning_language}.\n\n"
		f"Questions (apply all of them to each document):\n{aspects}\n\n"
		"Return exactly one entry per document id (" + ", ".join(rows_by_id) + "), each with exactly one result per key, "
		"an integer score from 1 to 5 and concise, specific reasoning. Support each score with evidence from that "
		"document's own text; quote exact errors or ambiguous phrases where relevant. Do not invent problems or "
		"overlook definite defects.\n\n"
		f"{documents}"
	)


def build_batch_summary_prompt(config, items):
	reasoning_language = config["review"].get("reasoning_language", "the language of the document")
	blocks = []
	for doc_id, scores, average_score in items:
		findings = "\n".join(f"- {aspect}: {score}/5. {reasoning}" for aspect, score, reasoning in scores)
		blocks.append(f"=== DOCUMENT {doc_id} === exact mean {average_score:.2f}/5\n{findings}")
	return (
		f"Write one summary per document in {reasoning_language}; the documents are independent, so summarize each "
		"only from its own findings. The application prepends the exact mean, so do not repeat or recalculate it. "
		"Each summary: very concise (no more than 32 words), reflecting the mean and the most important strength "
		"or weakness; surface a serious low-scoring issue even when the mean is high; no numeric scores; no filler. "
		"Return exactly one entry per document id.\n\n" + "\n\n".join(blocks)
	)


def review_batch(client, config, model, summary_model, rows):
	"""Reviews several documents in one request; returns [(row, (scores, average, summary) | Exception)]."""
	rows_by_id = batch_ids(rows)
	try:
		review = request_structured(
			client, config, model, build_batch_prompt(config, rows_by_id), BatchReviewSchema,
			config["review"]["system_prompt"],
		)
	except Exception as error:
		return [(row, error) for row in rows]

	by_id = {item.document.strip().upper(): item for item in review.documents}
	valid = {}
	outcome = {}
	for doc_id, row in rows_by_id.items():
		item = by_id.get(doc_id)
		try:
			if item is None:
				raise ValueError(f"No result for document {doc_id} in the batch answer.")
			scores = validated_scores(config, ReviewSchema(results=item.results))
			valid[doc_id] = (scores, sum(score for _, score, _ in scores) / len(scores))
		except Exception as error:
			outcome[doc_id] = error

	if valid:
		try:
			summaries = request_structured(
				client, config, summary_model,
				build_batch_summary_prompt(config, [(d, s, a) for d, (s, a) in valid.items()]),
				BatchSummarySchema,
				"You write concise, evidence-based summaries of thesis-description reviews. Return only the requested JSON.",
			)
			summary_by_id = {item.document.strip().upper(): item.summary.strip() for item in summaries.summaries}
		except Exception as error:
			summary_by_id = {}
			for doc_id in valid:
				outcome[doc_id] = error
		for doc_id, (scores, average_score) in valid.items():
			if doc_id in outcome:
				continue
			summary = summary_by_id.get(doc_id)
			if summary:
				outcome[doc_id] = (scores, average_score, f"Average {average_score:.2f}/5. {summary}")
			else:
				outcome[doc_id] = ValueError(f"No summary for document {doc_id} in the batch answer.")
	return [(row, outcome[doc_id]) for doc_id, row in rows_by_id.items()]


def review_single(client, config, model, summary_model, row):
	try:
		body = document_body(row)
		review = request_review(client, config, model, build_prompt(config, row, body))
		scores = validated_scores(config, review)
		average_score, summary = request_summary(client, config, summary_model, scores)
		return row, (scores, average_score, summary)
	except Exception as error:
		return row, error


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


def openai_settings():
	"""Returns (settings, missing env names)."""
	missing = [name for name in (OPENAI_ENV_KEY, OPENAI_ENV_URL) if not os.environ.get(name)]
	settings = {
		"api_key": os.environ.get(OPENAI_ENV_KEY),
		"base_url": os.environ.get(OPENAI_ENV_URL),
	}
	return settings, missing


def main(argv=None):
	args = parse_args(argv)
	config = load_config(args.config)
	timeout = config["llm"].get("timeout", 120)
	model = args.model or config["llm"]["model"]

	if args.openai:
		settings, missing = openai_settings()
		if missing:
			print(
				"ERROR: --openai needs these environment variables, which are not set: " + ", ".join(missing),
				file=sys.stderr,
			)
			return 2
		try:
			client = OpenAIClient(settings["api_key"], settings["base_url"], timeout)
		except ImportError:
			print("ERROR: the 'openai' Python package is not installed (pip install openai).", file=sys.stderr)
			return 2
	else:
		if not os.environ.get("GEMINI_API_KEY"):
			print("ERROR: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
			return 2
		client = genai.Client(http_options=types.HttpOptions(timeout=timeout * 1000))

	connection = sqlite3.connect(config["database"]["path"])
	connection.row_factory = sqlite3.Row
	ensure_schema(connection)
	aspects = [aspect["key"] for aspect in config["review"]["aspects"]]
	rows = pending_documents(connection, model, aspects, args.limit, args.filename)
	if not rows:
		print("No descriptions need review.")
		connection.close()
		return 1 if args.filename else 0

	stored = failures = 0
	batch_size = args.batch or 1
	summary_model = args.summary_model or model
	if summary_model != model:
		print(f"Aspects: {model}; summaries: {summary_model}")
	processed = 0
	for start in range(0, len(rows), batch_size):
		chunk = rows[start:start + batch_size]
		first, last = start + 1, start + len(chunk)
		label = f"{first}" if first == last else f"{first}-{last}"
		print(f"[{label}/{len(rows)}] Reviewing {', '.join(row['filename'] for row in chunk)} with {model}")
		if batch_size == 1:
			results = [review_single(client, config, model, summary_model, chunk[0])]
		else:
			results = review_batch(client, config, model, summary_model, chunk)
		for row, outcome in results:
			processed += 1
			if isinstance(outcome, Exception):
				failures += 1
				print(f"ERROR: Review failed for {row['filename']}: {outcome}", file=sys.stderr)
				continue
			scores, average_score, summary = outcome
			try:
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
	print(f"Review finished: processed {processed}, stored {stored}, failed {failures}.")
	return 1 if failures else 0


if __name__ == "__main__":
	raise SystemExit(main())
