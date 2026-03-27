# PDF Review Workflow

This script reviews thesis-task PDF files and exports an evaluation workbook with three sheets:

- `reviews`: one row per PDF with extracted metadata, automatic checks, language and grammar/spelling metrics, and empty manual review columns
- `rubric`: explains every automatic check and its pass rule
- `summary`: aggregate counts and average scores

## What It Checks

The script detects the document language (`hu` or `en`) from extracted text, then applies language-specific checks.

Automatic checks are split into two groups:

- `formal`: heading, student name, title, advisor, date, page count, task-list presence
- `content`: objective paragraph length, literature/background task, implementation/model task, evaluation task, report/presentation task, reasonable task count

Spell and grammar checks are performed by LanguageTool. By default the script uses the public API (`--spellcheck auto`) and picks `hu-HU` or `en-US` based on detected language.

Optional LLM check is supported with an OpenAI-compatible API (`--llm-check openai`).
Important: your API does not need native PDF support, because the script first extracts plain text from PDF and sends text to the API.

LLM prompts must be loaded from a file with `--llm-prompt-file`. If not specified, LLM review is skipped. A ready-to-use template is provided in `scraper/app/llm_prompt.txt`.
The file is used as the `system` role message. Dynamic data (language, title, full text) is sent in the `user` role message by the script.

Spell checking is optional. By default it is skipped. If you want automated spell checking, install `language_tool_python` and run with `--spellcheck auto`.

## Usage

Install required Python packages in your active environment:

```bash
/home/gume/diptervek/.venv/bin/pip install pypdf pymupdf pdfplumber openpyxl language_tool_python
```

Run from the repository root:

```bash
/home/gume/diptervek/.venv/bin/python scraper/app/review_pdfs.py \
  --input-dir data/td \
  --output pdf_review.xlsx \
  --txt-output-dir extracted_txt \
  -v
```

Verbose levels:

- `-v`: file-level progress and output paths
- `-vv`: detailed per-file check summary (language, scores, spell/grammar status, LLM status)

Text export option:

- `--txt-output-dir <dir>`: saves extracted PDF text as `.txt` files in the specified directory, with the same base filename as the PDF.

PDF extractor selection:

- `--pdf-extractor auto`: default, fallback chain `fitz -> pdfplumber -> pypdf`
- `--pdf-extractor fitz`: force PyMuPDF text/blocks adaptive mode
- `--pdf-extractor pdfplumber`: force pdfplumber extraction (requires `pdfplumber` package)
- `--pdf-extractor pypdf`: force pypdf extraction

Force local LanguageTool backend instead of public API:

```bash
/home/gume/diptervek/.venv/bin/python scraper/app/review_pdfs.py \
  --input-dir data/td \
  --output pdf_review.xlsx \
  --spellcheck languagetool
```

Optional OpenAI-compatible second check (auto-enabled when OpenAI flags are complete):

```bash
OPENAI_API_KEY="your_password_or_api_key" \
/home/gume/diptervek/.venv/bin/python scraper/app/review_pdfs.py \
  --input-dir data/td \
  --output pdf_review.xlsx \
  --openai-base-url https://api.openai.com \
  --openai-model gpt-4o-mini \
  --llm-prompt-file scraper/app/llm_prompt.txt
```

LLM mode behavior:

- `--llm-check` defaults to `auto`, so you usually do not need to set it.
- OpenAI review is used automatically when `--openai-base-url` and `--llm-prompt-file` are provided.
- You can still force behavior with `--llm-check openai` or disable with `--llm-check none`.
- If no API key is provided, a dummy key is used (helpful for local AI endpoints that ignore auth).

No placeholders are required in the template file.

## Output Columns

The main review sheet contains:

- basic metadata: file, title, student, advisor, date, degree level
- language metadata: detected language (`hu` or `en`)
- automatic metrics: page count, word count, bullet count, formal score, content score
- language quality metrics: total language issues, grammar issues, spelling issues
- optional LLM columns: `llm_check_status`, `llm_score`, `llm_verdict`, `llm_summary`
- automatic flags: missing fields, missing tasks, suspicious structure
- manual columns: `manual_formal_review`, `manual_spell_review`, `manual_content_review`, `manual_notes`

## Practical Limits

- PDF text extraction depends on the PDF encoding and layout.
- Content checks are heuristic; they are useful for triage, not final academic judgement.
- Spell and grammar checking via public API may not be acceptable for confidential documents. In that case, use `--spellcheck languagetool` with a local backend.
- If you run locally, choose a writable output path such as `pdf_review.xlsx`. The repository's `data/db` folder may be owned by the container user.