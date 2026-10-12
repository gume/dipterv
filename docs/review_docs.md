# Review of descriptions (`review_docs.py`)

`scraper/app/review_docs.py` reviews the text of task descriptions that are already in the `extract` table. It does no PDF handling.

## Reviewed text

The body sent to the model is built from `extract` in this order: `thesis_title`, `problem_background`, `project_goal`, `task_intro`, and `tasks_json` (numbered list). The degree and faculty come from `import`.

## Selection

Candidates are `import` rows joined to `extract` rows with a non-NULL `thesis_title`. A description is pending when the model reviewer is missing any configured aspect in `reviews`. This also requeues existing reviews when new aspects are added. Results are kept per model; complete reviews are skipped. `--filename` explicitly reruns that file and replaces the model's prior aspect results.

## Results

For each aspect configured in `review.aspects`, the model returns a 1-5 score and reasoning, stored in `reviews` (`reviewer` = model id, `aspect` = key, `score`, `result` = reasoning). The script gives no overall ok/notok verdict; that go/no-go decision is made by human reviewers in `review_verdict`. All rows of one document are written in a single transaction; a failed request or an incomplete answer stores nothing, so the document stays pending. See [database.md](database.md) for the tables.

## Usage

`GEMINI_API_KEY` must be set in the environment.

```bash
docker compose run --rm -e GEMINI_API_KEY playwright-runner \
	python3 /app/review_docs.py --limit 10 --model gemini-3.5-flash-lite
```

| Option | Meaning |
| --- | --- |
| `--limit N` | Review at most N pending descriptions. |
| `--model ID` | Model to use; also the reviewer id. Defaults to `llm.model` from the config. |
| `--filename NAME` | Review only this `import` filename; an existing review by the same reviewer is replaced. |
| `--config PATH` | Alternative TOML config (default `scraper/app/review_config.toml`). |

Exit code: 0 on success, 1 if any review failed (or `--filename` matched nothing), 2 if the API key is missing.

## Configuration (`review_config.toml`)

| Key | Purpose |
| --- | --- |
| `database.path` | SQLite file. |
| `llm.model`, `llm.temperature`, `llm.timeout`, `llm.retries` | Model settings; failed requests are retried with backoff (60 s on rate limiting). |
| `review.reasoning_language` | Language requested for the reasoning. |
| `review.system_prompt` | Strict shared 1-5 scoring anchors, evidence requirements and reviewer instructions. |
| `[[review.aspects]]` | `key` and `prompt` of each reviewed aspect. The current rubric covers goal clarity, task specificity, scope feasibility, strict language accuracy, degree appropriateness, AI promptability, and task ambiguity. |

## Functions

| Function | Purpose |
| --- | --- |
| `pending_documents` | Selects documents to review (pending, or one `--filename`). |
| `document_body` | Builds the reviewed text. |
| `build_prompt` | Builds the user prompt from the aspects, degree/faculty and body. |
| `request_review` | Calls Google GenAI with a JSON schema and retries. |
| `validated_scores` | Ensures every configured aspect has a 1-5 score. |
| `store_review` | Replaces the reviewer's rows for the document. |
