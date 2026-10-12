# Database

## File and deployment

The application database is `descriptions.sqlite`, stored at `/db/descriptions.sqlite` inside both Docker services. In the repository, `/db` is mounted from `data/db`, so the host-side file is `data/db/descriptions.sqlite`. The database is runtime data and `data*` is ignored by Git.

The scraper and PHP web service share this mount. The scraper sets `/db` ownership to `www-data` after importing; the web service entrypoint also sets ownership of `/db` to `www-data` at startup.

The database setup creates the current schema and does not migrate older databases. Delete `data/db/descriptions.sqlite` manually before initializing this schema if an older database is present.

## Schema

`scraper/app/create_db.py` creates and syncs the following tables:

### `import`

One row per student task-description version. The composite key `(neptun_code, version)` is unique; `filename` is also unique for compatibility with the existing web UI.

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

One row per `(neptun_code, version)`, with the same composite primary key as `import`.

| Column | Purpose |
| --- | --- |
| `neptun_code`, `version` | Identify the imported task-description version. |
| `status` | Overall review status, such as `OK` or `Not OK`. |
| `ekovacsG`, `eGuszti`, `eGume`, `ePali` | Reviewer remarks stored as text. |

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

## Compatibility view

`dipterv` is a view joining `import`, `reviews`, and `extract`. It exposes the legacy names used by existing code, including `verzio`, `hallgato`, `konzulens`, and `szint`, alongside the new metadata fields. An `INSTEAD OF UPDATE` trigger routes changes to `status` and reviewer columns into `reviews`, so the existing PHP update endpoint continues to work. `filtered_dipterv` retains its previous filtering behavior.

The PDF itself is served from `/data` (host-side `data/td`), not from SQLite; SQLite stores its filename and metadata.

## Readers and writers

| Component | Access | Behavior |
| --- | --- | --- |
| `scraper/app/prepare_docs.py` and `scraper/app/create_db.py` | Write | Read eligible task rows from Excel and reconcile the `import` table. `prepare_docs.py` syncs metadata before downloading PDFs and syncs any resulting filename changes afterward. |
| `scraper/app/extract_docs.py` | Reads `import`; writes `extract` | Selects pending filenames from the database, sends PDFs and templates to the configured Google GenAI model, and stores structured extraction results. |
| `webgui/html/data.php` | Reads | Selects all rows from `dipterv` and returns JSON to the web pages. It opens SQLite with create/read-write flags although it only runs a `SELECT`. |
| `webgui/html/browse.html` | Reads via `data.php`; writes via `update.php` | Displays descriptions and submits review fields/status. |
| `webgui/html/review.html` | Reads via `data.php`; writes via `update.php` | Loads descriptions for review and posts reviewer remarks/status changes. |
| `webgui/html/update.php` | Writes | Updates a reviewer field or `status` through the `dipterv` view and trigger. |
| `scraper/app/notok.py` | Reads | Selects `Not OK` rows from `dipterv` and prints them grouped by advisor. |

## Import behavior

The importer processes workbook rows in the portal's pending-approval statuses. If the expected PDF is already present in `/data`, `prepare_docs.py` skips its download and still checks/syncs its database record. Missing records and fields are reported as additions. Differences from existing non-empty values are reported as warnings, then the workbook value replaces the stored import value. Review data stays in `reviews` and is not replaced during normal import syncs.
