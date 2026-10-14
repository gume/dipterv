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
| `degree` | `Képzés`. |
| `faculty` | `Szak`. |
| `subject` | `Tantárgy`. |
| `title_hu` | `Téma magyar címe`. |
| `title_en` | `Téma angol címe`. |

### `reviews`

One row per reviewer and aspect of an imported description: primary key `(neptun_code, version, reviewer, aspect)`. `(neptun_code, version)` identifies the `import` row.

| Column | Purpose |
| --- | --- |
| `reviewer` | Reviewer id. AI reviewers use the model id (e.g. `gemini-3.5-flash-lite`); human reviewers use an id from `reviewers`. |
| `aspect` | Reviewed aspect, e.g. `goal_clarity`. Human remarks use the aspect `remark`. |
| `result` | Review text (reasoning or remark). |
| `score` | Integer 1-5. AI aspects: 1 unacceptable, 3 average, 5 superior. Human `remark` rows: the reviewer's star rating, set only in the web UI review pane (NULL = not rated). |
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

### `extract`

One row per extracted PDF, keyed by `filename`. `template_status` stores the template check result: NULL = not extracted, 0 = everything is ok, 1 = minor problems, 2 = critical problems.

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

Run the extractor from the scraper container with `GEMINI_API_KEY` set:

```bash
docker compose run --rm -e GEMINI_API_KEY playwright-runner \
	python3 /app/extract_docs.py --limit 10 --model gemini-3.5-flash-lite
```

Available options include `--limit`, `--model`, `--timeout`, `--templates-dir`, `--data-dir`, `--database`, and `--json`. With no `--limit`, all pending database PDFs are processed. Rows already present in `extract` are excluded before applying the limit; missing PDF files are warned about and do not consume it.

The PDF itself is served from `/data` (host-side `data/td`), not from SQLite; SQLite stores its filename and metadata.

## Readers and writers

| Component | Access | Behavior |
| --- | --- | --- |
| `scraper/app/prepare_docs.py` and `scraper/app/create_db.py` | Write | Read eligible task rows from Excel and reconcile the `import` table. `prepare_docs.py` syncs metadata before downloading PDFs and syncs any resulting filename changes afterward. |
| `scraper/app/extract_docs.py` | Reads `import`; writes `extract` | Selects pending filenames from the database, sends PDFs and templates to the configured Google GenAI model, and stores structured extraction results. |
| `scraper/app/review_docs.py` | Reads `import`, `extract`; writes `reviews`, `review_summaries` | Stores per-aspect scores/reasoning and a per-model average/summary; see [review_docs.md](review_docs.md). |
| `webgui/html/data.php` | Reads | Returns one JSON object per `import` row with its `extract` format check (`template_status` and the cause list), `review_verdict`, human remarks and star ratings (`remarks` and `remark_scores`, keyed by reviewer), and AI scores/summaries/averages keyed by model. Opens the database read-only. |
| `webgui/html/reviewers.php` | Reads | Returns the `reviewers` list. |
| `webgui/html/body.php` | Reads | Returns the extracted description body (same text as `review_docs.py` reviews) for the text view. |
| `webgui/html/update.php` | Writes | `action=remark`: sets the human remark text and/or the 1-5 rating of the chosen reviewer in `reviews`. A field that is not sent keeps its stored value; the row is deleted when both text and rating are empty. `action=verdict`: sets `review_verdict.status`. Uses prepared statements and validates the reviewer, rating and verdict values. |
| `webgui/html/index.html` | Via the PHP endpoints | Right side: PDF/text viewer with, below it, the review pane (text box and 5-star rating) of the selected reviewer for the current document. The text is kept in sync with the table (or review page) text; the rating is set only here. |
| `webgui/html/browse.html`, `review.html` | Via the PHP endpoints | Overview table and one-by-one review. In the table each human reviewer column shows the read-only rating above the text and sorts by it. Styles are in `style.css`, shared code in `common.js`; the PDF/text pane is in `index.html`. |
| `scraper/app/notok.py` | Reads | Prints the descriptions with verdict `nogo`, grouped by supervisor, with the human remarks. |
| `scraper/app/manage_reviews.py` | Reads/deletes `reviews`, `review_summaries` | `--list` shows each reviewer (AI model or human) with description count, review rows, summaries, average score and totals. `--remove REVIEWER` deletes that reviewer from both tables after confirmation (`--yes` skips it); human reviewers from `reviewers` need `--force`. `review_verdict` is untouched. |

## Import behavior

The importer processes workbook rows in the portal's pending-approval statuses. If the expected PDF is already present in `/data`, `prepare_docs.py` skips its download and still checks/syncs its database record. Missing records and fields are reported as additions. Differences from existing non-empty values are reported as warnings, then the workbook value replaces the stored import value. Review data stays in `reviews` and `review_verdict` and is not replaced during normal import syncs; if a record's key changes, its review rows are moved to the new key.

See also [extract_docs.md](extract_docs.md) and [review_docs.md](review_docs.md).
