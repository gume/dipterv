# Database

## File and deployment

The application database is `descriptions.sqlite`, stored at `/db/descriptions.sqlite` inside both Docker services. In the repository, `/db` is mounted from `data/db`, so the host-side file is `data/db/descriptions.sqlite`. The database is runtime data and `data*` is ignored by Git.

The scraper and PHP web service share this mount. The scraper sets `/db` ownership to `www-data` after importing; the web service entrypoint also sets ownership of `/db` to `www-data` at startup.

The database setup creates the current schema and does not migrate older databases. To move an existing database that has the old one-row-per-description `reviews` table, run `python3 /app/migrate_reviews.py` in the scraper container. It drops the old `reviews` table (refusing if it has rows unless `--force`), creates `reviews`, `review_summaries`, `review_verdict` and `reviewers`, and drops the old `dipterv` and `filtered_dipterv` compatibility views; other tables are untouched. For an already migrated database, the script only adds the missing summary table and reviewer entries.

## Schema

`scraper/app/create_db.py` creates and syncs the following tables:

### `import`

One row per student task-description version. The composite key `(neptun_code, version)` is unique; `filename` is also unique because the web UI and extraction address a description by it.

| Column | Purpose |
| --- | --- |
| `neptun_code` | `Hallgató Neptun kódja` from Excel. |
| `row_id` | Zero-based index of the data row in the workbook. |
| `filename` | PDF filename associated with the task description. |
| `version` | Version parsed from the trailing number in `filename`. |
| `student_name` | `Hallgató neve`. |
| `supervisor_name` | `Konzulens neve`. |
| `supervisor_code` | `Konzulens Neptun kódja` (uppercase); matches `supervisors.neptun_code` and is what the supervisor web container filters on. |
| `degree` | `Képzés`. |
| `faculty` | `Szak`. |
| `subject` | `Tantárgy`. |
| `title_hu` | `Téma magyar címe`. |
| `title_en` | `Téma angol címe`. |
| `portal_status` | `Feladatkiírás státusza` on the university portal: `accepted` (`Tanszékvezető jóváhagyta`), `rejected` (`Konzulensi feltöltésre vár, mert a tanszékvezető elutasította`), `undecided` (`Feltöltve, tanszékvezetői jóváhagyásra vár`), or NULL if unavailable. |
| `portal_status_date` | `Feladatkiírás jóváhagyás/elutasítás dátuma` from Excel (normalized `YYYY-MM-DD HH:MM:SS`), or NULL if unavailable. |

### `reviews`

One row per reviewer and aspect of an imported description: primary key `(neptun_code, version, reviewer, aspect)`. `(neptun_code, version)` identifies the `import` row.

| Column | Purpose |
| --- | --- |
| `reviewer` | Reviewer id. AI reviewers use the model id (e.g. `gemini-3.5-flash-lite`); human reviewers use an id from `reviewers`. |
| `aspect` | Reviewed aspect: standard 1-5 quality rubrics (`goal_clarity`, `task_specificity`, `scope_feasibility`, `language_quality`, `degree_appropriateness`, `ai_promptability`, and `structure_conformance`), blind degree fitting scores (`fit_score_bprof`, `fit_score_bsc`, `fit_score_msc`), or human remarks (`remark`). |
| `result` | Review text (reasoning or remark). |
| `score` | Integer score. AI quality aspects: 1 (unacceptable) to 5 (superior). Blind degree fitting aspects: 0 to 100%. Human `remark` rows: the reviewer's star rating, set only in the web UI review pane (NULL = not rated). |
| `updated_at` | UTC timestamp. |

### `review_verdict`

One overall go/no-go verdict per description, decided by humans through the web UI: primary key `(neptun_code, version)`. AI reviews do not write here. A description without a row is undecided.

| Column | Purpose |
| --- | --- |
| `status` | `go`, `nogo`, or `undecided`. |
| `summary` | Optional note. |
| `updated_at` | UTC timestamp. |

### `review_summaries`

One AI summary per description and model: primary key `(neptun_code, version, reviewer)`. `average_score` is calculated from that model's configured aspect scores; `summary` is a concise, evidence-based synthesis that includes the exact average. The web UI shows each model's average as a sortable AI column, with the summary on hover.

| Column | Purpose |
| --- | --- |
| `average_score` | Arithmetic mean of the model's aspect scores. |
| `summary` | Short evaluation highlighting the overall quality and any major weakness. |
| `updated_at` | UTC timestamp. |

### `reviewers`

The human reviewers offered by the web UI: `id` (primary key, used in `reviews.reviewer`) and `name` (display name). The web UI only lets the user pick an identity from this list; there is no authentication. `create_db.py` seeds `kovacsg`, `guszti`, `gume`, `pali` (`INSERT OR IGNORE`); add or rename rows with SQL.

### `supervisors`

Logins of the supervisor web container, filled by `create_db.py` from the workbook's `Konzulens Neptun kódja` / `Konzulens neve` columns (all rows). `neptun_code` is the primary key; `name` is the portal name and is how a supervisor is matched to `import.supervisor_name`. `alt_name` is optional and, when set, is shown instead of `name` (to fix missing "Dr." or wrong capitalization in the portal data); later imports keep it. For now the password equals the Neptun code. Managed with `manage_supervisors.py`: `--list`, `--alt-name NEPTUN NAME` (empty NAME clears), `--add NEPTUN NAME`, `--remove NEPTUN`.

### `settings`

Key/value settings. `supervisor_ai_model` is the AI reviewer id whose review supervisors see (set with `manage_supervisors.py --ai-model MODEL`); when unset, the most recently updated AI review of the description is shown.

### `extract`

One row per extracted PDF, keyed by `filename`. `template_status` stores the template check result: NULL = not extracted, 0 = everything is ok, 1 = minor problems, 2 = critical problems. `page_count` is the number of PDF pages; anything but exactly one page is critical and adds a `Page count: ...` entry to `layout_discrepancies_json`. Rows extracted before this column existed are backfilled (without the model) on the next `extract_docs.py` run.

| Column | Purpose |
| --- | --- |
| `detected_template` | Selected language/template identifier. |
| `header_dept_head`, `thesis_type`, `student_suffix` | Exact matched text for the corresponding header, thesis-type, and student-suffix boilerplate rules. |
| `task_intro`, `supervisor_label`, `dept_head_title` | Exact matched text for task introduction, supervisor label, and department-head title rules. |
| `footer_university`, `footer_faculty`, `footer_department` | Exact matched text for the university, faculty, and department footer rules. |
| `missing_boilerplate_rules_json` | JSON list of required boilerplate rules not found. |
| `layout_discrepancies_json` | JSON list of layout issues reported by the model. |
| `student_name`, `student_status`, `thesis_title` | Extracted student and assignment details. |
| `problem_background`, `project_goal`, `tasks_json` | Extracted background, goal, and task list. `tasks_json` is a JSON array. |
| `supervisor`, `cosupervisor`, `department_head`, `issue_date` | Extracted supervisor and issue details. |
| `university_logo_present`, `department_logo_present`, `signature_space_present` | Nullable integer booleans for template visual elements. |
| `university_logo_box_2d_json`, `department_logo_box_2d_json`, `signature_space_box_2d_json` | Nullable JSON arrays `[ymin, xmin, ymax, xmax]`, normalized to 0-1000, for each visual element. No image crops or image files are stored. |
| `keyword1`, `keyword2`, `keyword3`, `keyword4`, `keyword5` | 5 most relevant keywords ordered by relevance, extracted from the assignment text (NULL if fewer than 5). |

### `description_topics`

Top 5 department topics synthesized from thesis keywords and titles by `compute_statistics.py`.

| Column | Purpose |
| --- | --- |
| `rank` | Topic rank (1 to 5). |
| `topic_name` | Name of the synthesized topic area. |
| `topic_description` | Short description of what this topic covers. |
| `thesis_count` | Number of matching thesis descriptions. |
| `percentage` | Percentage of total descriptions. |
| `top_keywords_json` | JSON list of characteristic keywords. |
| `updated_at` | UTC timestamp. |

### `description_metric_distributions`

Summary statistics and histogram buckets for extracted and review metrics.

| Column | Purpose |
| --- | --- |
| `metric_key` | Metric identifier (e.g. `language_quality`, `structure_conformance`, `fit_msc`, `fit_bsc`, `fit_bprof`). |
| `metric_label` | Human-readable metric display name. |
| `source_type` | Data source (`extract` or `review`). |
| `average_value` | Arithmetic mean. |
| `min_value`, `max_value` | Range bounds. |
| `total_samples` | Number of data points. |
| `histogram_json` | JSON array of bucket objects `{bucket, count, percentage}`. |
| `updated_at` | UTC timestamp. |

### `description_fun_facts`

Data-driven trivia and high-level insights generated by `compute_statistics.py`.

| Column | Purpose |
| --- | --- |
| `category` | Category tag (e.g. `topics`, `methodology`, `quality`, `trivia`). |
| `title` | Catchy headline for the fact. |
| `fact_text` | Descriptive insight text. |
| `highlight_stat` | Short stat pill (e.g. `78%`, `3.8 / 5`). |
| `updated_at` | UTC timestamp. |

Run the extractor from the scraper container with `GEMINI_API_KEY` set:

```bash
docker compose run --rm -e GEMINI_API_KEY playwright-runner \
	python3 /app/extract_docs.py --limit 10 --model gemini-3.5-flash-lite
```

Available options include `--limit`, `--model`, `--timeout`, `--templates-dir`, `--data-dir`, `--database`, and `--json`. With no `--limit`, all pending database PDFs are processed. Rows that are missing a required extracted feature (e.g. their keywords were never extracted) are treated as pending and merged again; completely extracted rows are excluded before applying the limit. Missing PDF files are warned about and do not consume it.

The PDF itself is served from `/data` (host-side `data/td`), not from SQLite; SQLite stores its filename and metadata.

## Readers and writers

| Component | Access | Behavior |
| --- | --- | --- |
| `scraper/app/prepare_docs.py` and `scraper/app/create_db.py` | Write | Read eligible task rows from Excel and reconcile the `import` table. `prepare_docs.py` syncs metadata before downloading PDFs and syncs any resulting filename changes afterward. |
| `scraper/app/extract_docs.py` | Reads `import`; writes `extract` | Selects pending filenames from the database, sends PDFs and templates to the configured Google GenAI model, and stores structured extraction results. |
| `scraper/app/review_docs.py` | Reads `import`, `extract`; writes `reviews`, `review_summaries` | Stores per-aspect scores/reasoning and a per-model average/summary; see [review_docs.md](review_docs.md). |
| `reviewer/html/data.php` | Reads | Returns one JSON object per `import` row with its `extract` format check (`template_status` and the cause list), `review_verdict`, human remarks and star ratings (`remarks` and `remark_scores`, keyed by reviewer), and AI scores/summaries/averages keyed by model. Opens the database read-only. |
| `supervisor/html/*.php` (`supervisor-gui`, port 8083) | Reads only | Supervisor login (Neptun code, password = Neptun code) and a page with the supervisor's descriptions: verdict (accepted/rejected/undecided), formal errors, human remarks in chronological order and one AI review. The database is mounted `:ro` and opened with `SQLITE3_OPEN_READONLY`. |
| `reviewer/html/reviewers.php` | Reads | Returns the `reviewers` list. |
| `reviewer/html/body.php` | Reads | Returns the extracted description body (same text as `review_docs.py` reviews) for the text view. |
| `reviewer/html/update.php` | Writes | `action=remark`: sets the human remark text and/or the 1-5 rating of the chosen reviewer in `reviews`. A field that is not sent keeps its stored value; the row is deleted when both text and rating are empty. `action=verdict`: sets `review_verdict.status`. Uses prepared statements and validates the reviewer, rating and verdict values. |
| `reviewer/html/index.html` | Via the PHP endpoints | Right side: PDF/text viewer with, below it, the review pane (text box and 5-star rating) of the selected reviewer for the current document. The text is kept in sync with the table (or review page) text; the rating is set only here. |
| `reviewer/html/browse.html`, `review.html` | Via the PHP endpoints | Overview table and one-by-one review. In the table each human reviewer column shows the read-only rating above the text and sorts by it. Styles are in `style.css`, shared code in `common.js`; the PDF/text pane is in `index.html`. |
| `scraper/app/notok.py` | Reads | Prints the descriptions with verdict `nogo`, grouped by supervisor, with the human remarks. |
| `scraper/app/manage_reviews.py` | Reads/deletes `reviews`, `review_summaries` | `--list` shows each reviewer (AI model or human) with description count, review rows, summaries, average score and totals. `--remove REVIEWER` deletes that reviewer from both tables after confirmation (`--yes` skips it); human reviewers from `reviewers` need `--force`. `review_verdict` is untouched. |

## Import behavior

The importer processes workbook rows in the portal's pending-approval statuses. If the expected PDF is already present in `/data`, `prepare_docs.py` skips its download and still checks/syncs its database record. Missing records and fields are reported as additions. Differences from existing non-empty values are reported as warnings, then the workbook value replaces the stored import value. Review data stays in `reviews` and `review_verdict` and is not replaced during normal import syncs; if a record's key changes, its review rows are moved to the new key.

See also [extract_docs.md](extract_docs.md) and [review_docs.md](review_docs.md).
