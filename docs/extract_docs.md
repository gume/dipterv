# Extraction of descriptions (`extract_docs.py`)

`scraper/app/extract_docs.py` sends the PDFs listed in the `import` table to a Google GenAI model and stores the structured result in `extract`. See [database.md](database.md) for the columns.

## Flow

1. Load every language template JSON from `scraper/app/templates` (`en.json`, `hu.json`) and build one prompt containing all templates.
2. Select pending filenames: `import` rows without an `extract` row, or rows with `template_status > 0` whose `detected_template` is not a current template id (rechecked after template changes). Missing PDFs in the data directory are warned about and do not count toward `--limit`.
3. For each PDF, call the model with a Pydantic response schema (`ThesisAssignmentSchema`), temperature 0. Models whose name contains `gemma` receive a 200 dpi image of the first page instead of the PDF. One retry after 60 s on a 429 rate-limit error.
4. Compute `template_status` and store the row with `INSERT OR REPLACE`.

## Template status

| Value | Meaning |
| --- | --- |
| NULL | Not extracted. |
| 0 | No missing boilerplate rules and no layout discrepancies. |
| 1 | Minor: no layout discrepancies and the missing rules match a set in `MINOR_MISSING_RULE_SETS` (currently only `task_intro`). |
| 2 | Critical: anything else, including a PDF with more than one page (`page_count`, counted locally with PyMuPDF). |

## Stored data

- Boilerplate fields: the exact matched text of each template rule, or NULL.
- `missing_boilerplate_rules_json`, `layout_discrepancies_json`: JSON lists.
- Content: `student_name`, `student_status`, `thesis_title`, `problem_background`, `project_goal`, `tasks_json`, supervisors, `department_head`, `issue_date`.
- Visual elements (`university_logo`, `department_logo`, `signature_space`): presence flag and a `[ymin, xmin, ymax, xmax]` box normalized to 0-1000. No image data is stored.

## Usage

`GEMINI_API_KEY` must be set in the environment.

```bash
docker compose run --rm -e GEMINI_API_KEY playwright-runner \
	python3 /app/extract_docs.py --limit 10 --model gemini-3.5-flash-lite
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--limit N` | all | Maximum number of pending PDFs to extract. |
| `--model ID` | `gemini-3.5-flash-lite` | Model ID. |
| `--timeout S` | 60 | Request timeout in seconds. |
| `--database PATH` | `/db/descriptions.sqlite` | SQLite file. |
| `--data-dir PATH` | `/data` | Directory with the PDFs. |
| `--templates-dir PATH` | `scraper/app/templates` | Template JSON directory. |
| `--reload [FILENAME]` | off | Re-extract and recheck all descriptions (or only FILENAME) regardless of existing rows. Missing values are added; changed values are overwritten with a warning. `--limit` still applies. |
| `--json` | off | Print each extracted result as JSON. |

Exit code is 1 if any extraction failed. Failed files are not stored and stay pending.

## Functions

| Function | Purpose |
| --- | --- |
| `load_templates` | Reads the template JSON files. |
| `pending_filenames`, `pending_pdf_filenames` | Select pending records, then those with an existing PDF, applying the limit. |
| `build_prompt` | Builds the prompt with all templates. |
| `make_pdf_part` | PDF bytes, or first-page PNG for Gemma models. |
| `extract_pdf` | Model call with retry on 429; validates the response. |
| `template_status` | Computes the 0/1/2 status. |
| `result_database_values` | Maps the result to `extract` columns. |
| `store_result` | Writes the row. |
