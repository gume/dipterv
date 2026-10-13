# Review of descriptions (`review_docs.py`)

`scraper/app/review_docs.py` reviews the text of task descriptions that are already in the `extract` table. It does no PDF handling.

## Reviewed text

The body sent to the model is built from `extract` in this order: `thesis_title`, `problem_background`, `project_goal`, `task_intro`, and `tasks_json` (numbered list). The degree and faculty come from `import`.

## Selection

Candidates are `import` rows joined to `extract` rows with a non-NULL `thesis_title`. A description is pending when the model reviewer is missing any configured aspect in `reviews`, has an obsolete aspect, or lacks a row in `review_summaries`. This also requeues existing reviews when aspects are added or changed. Results are kept per model; complete reviews are skipped. `--filename` explicitly reruns that file and replaces the model's prior results.

## Results

For each aspect configured in `review.aspects`, the model returns a 1-5 score and reasoning, stored in `reviews` (`reviewer` = model id, `aspect` = key, `score`, `result` = reasoning). A second model call produces a concise synthesis using the exact arithmetic mean computed from those scores. The mean and synthesis are stored in `review_summaries`, separately for each model, and the web UI shows the summary when hovering over that model's average. The script gives no overall go/no-go verdict; that decision is made by human reviewers in `review_verdict`. Aspect results and summary are written in one transaction; a failed or incomplete response stores nothing, so the description stays pending. See [database.md](database.md) for the tables.

## Usage

`GEMINI_API_KEY` must be set in the environment (Google, the default).

```bash
docker compose run --rm -e GEMINI_API_KEY playwright-runner \
	python3 /app/review_docs.py --limit 10 --model gemini-3.5-flash-lite
```

| Option | Meaning |
| --- | --- |
| `--limit N` | Review at most N pending descriptions. |
| `--model ID` | Model to use; also the reviewer id. Defaults to `llm.model` from the config. |
| `--openai` | Use an OpenAI-compatible chat-completions API instead of Google; see below. |
| `--filename NAME` | Review only this `import` filename; an existing review by the same reviewer is replaced. |
| `--config PATH` | Alternative TOML config (default `scraper/app/review_config.toml`). |

Exit code: 0 on success, 1 if any review failed (or `--filename` matched nothing), 2 if the API key is missing.

### OpenAI-compatible API

With `--openai` the same prompts, scoring, summary, retry and storage code is used; only the request transport differs. Settings come from environment variables only; if any is unset, the run stops (exit code 2) and lists the missing names:

| Variable | Meaning |
| --- | --- |
| `OPENAI_API_KEY` | API key. |
| `OPENAI_BASE_URL` | Endpoint, e.g. `https://api.openai.com/v1` or a local server. |

The model comes from `--model`, or `llm.model` in the config if omitted, so pass `--model` with `--openai`. The model id is the reviewer id, as with Google. The server must support chat completions with `response_format={"type": "json_object"}`; the expected JSON schema is passed in the system prompt and the answer is validated afterwards, so a malformed reply is retried like any other failure. HTTP 429 and a `Retry-After` header are honoured.

## Configuration (`review_config.toml`)

| Key | Purpose |
| --- | --- |
| `database.path` | SQLite file. |
| `llm.model`, `llm.temperature`, `llm.timeout`, `llm.retries` | Model settings; failed requests are retried with backoff (60 s on rate limiting). |
| `review.reasoning_language` | Language requested for the reasoning. |
| `review.system_prompt` | Strict shared 1-5 scoring anchors, evidence requirements and reviewer instructions. |
| `[[review.aspects]]` | `key` and `prompt` of each reviewed aspect. The current rubric covers goal clarity, task specificity (including ambiguity), scope feasibility, strict language accuracy, degree appropriateness, and AI promptability. |

## Functions

| Function | Purpose |
| --- | --- |
| `pending_documents` | Selects documents to review (pending, or one `--filename`). |
| `document_body` | Builds the reviewed text. |
| `build_prompt` | Builds the user prompt from the aspects, degree/faculty and body. |
| `request_structured` | One structured-output call with retries; the only function that knows the transport (Google client or `OpenAIClient`). |
| `request_review` | Aspect scoring call. |
| `validated_scores` | Ensures every configured aspect has a 1-5 score. |
| `store_review` | Replaces the reviewer's rows for the document. |
