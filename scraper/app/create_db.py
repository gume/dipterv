#!/usr/bin/env python
# -*- coding: utf-8 -*-

import glob
import os
import re
import sqlite3
import sys

from openpyxl import load_workbook


DATABASE_PATH = "/db/descriptions.sqlite"
PENDING_STATUSES = {
    "Feltöltve, tanszékvezetői jóváhagyásra vár",
    "Nincs beadva, mert a tanszékvezető nem hagyta jóvá",
}
IMPORT_COLUMNS = (
    "neptun_code",
    "row_id",
    "filename",
    "version",
    "student_name",
    "supervisor_name",
    "degree",
    "faculty",
    "subject",
    "title_hu",
    "title_en",
)
REVIEW_COLUMNS = ("status", "ekovacsG", "eGuszti", "eGume", "ePali")
EXTRACT_COLUMNS = {
    "template_status": "INTEGER",
    "detected_template": "TEXT",
    "header_dept_head": "TEXT",
    "thesis_type": "TEXT",
    "student_suffix": "TEXT",
    "task_intro": "TEXT",
    "supervisor_label": "TEXT",
    "dept_head_title": "TEXT",
    "footer_university": "TEXT",
    "footer_faculty": "TEXT",
    "footer_department": "TEXT",
    "missing_boilerplate_rules_json": "TEXT",
    "layout_discrepancies_json": "TEXT",
    "student_name": "TEXT",
    "student_status": "TEXT",
    "thesis_title": "TEXT",
    "problem_background": "TEXT",
    "project_goal": "TEXT",
    "tasks_json": "TEXT",
    "supervisor": "TEXT",
    "cosupervisor": "TEXT",
    "department_head": "TEXT",
    "issue_date": "TEXT",
    "university_logo_present": "INTEGER",
    "university_logo_box_2d_json": "TEXT",
    "department_logo_present": "INTEGER",
    "department_logo_box_2d_json": "TEXT",
    "signature_space_present": "INTEGER",
    "signature_space_box_2d_json": "TEXT",
}


def normalize_text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def parse_version(filename):
    match = re.search(r"-(\d+)\.pdf$", filename or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def load_import_rows(workbook_path, data_dir="/data"):
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    sheet = workbook.active
    headers = [normalize_text(cell) for cell in next(sheet.iter_rows(min_row=4, max_row=4, values_only=True))]
    required_headers = (
        "Hallgató Neptun kódja",
        "Hallgató neve",
        "Konzulens neve",
        "Képzés",
        "Szak",
        "Tantárgy",
        "Téma magyar címe",
        "Téma angol címe",
        "Feladatkiírás verziószáma",
        "Feladatkiírás státusza",
        "Téma oktatói szerkesztő oldalának címe (URL) a portálon",
    )
    missing_headers = [header for header in required_headers if header not in headers]
    if missing_headers:
        workbook.close()
        raise ValueError("Workbook is missing required columns: " + ", ".join(missing_headers))
    header_indexes = {header: headers.index(header) for header in required_headers}

    records = []
    for row_id, cells in enumerate(sheet.iter_rows(min_row=5, values_only=True)):
        row = {header: cells[index] if index < len(cells) else None for header, index in header_indexes.items()}
        if normalize_text(row["Feladatkiírás státusza"]) not in PENDING_STATUSES:
            continue

        neptun_code = normalize_text(row["Hallgató Neptun kódja"])
        url = normalize_text(row["Téma oktatói szerkesztő oldalának címe (URL) a portálon"])
        slug_match = re.search(r"Theses/([^/]+)/", url or "")
        if not neptun_code or not slug_match:
            print(f"WARNING: Skipping workbook row {row_id}: missing Neptun code or task URL.")
            continue

        try:
            sheet_version = int(float(row["Feladatkiírás verziószáma"]))
        except (TypeError, ValueError):
            sheet_version = None

        slug = slug_match.group(1)
        existing_files = glob.glob(os.path.join(data_dir, f"{slug}-Feladatkiiras-*.pdf"))
        if sheet_version:
            filename = f"{slug}-Feladatkiiras-{sheet_version}.pdf"
        elif existing_files:
            filename = max(existing_files, key=lambda path: parse_version(os.path.basename(path)) or 0)
            filename = os.path.basename(filename)
        else:
            print(f"WARNING: Skipping workbook row {row_id}: cannot determine PDF version.")
            continue

        version = parse_version(filename)
        if version is None:
            print(f"WARNING: Skipping workbook row {row_id}: cannot parse version from {filename}.")
            continue

        records.append({
            "neptun_code": neptun_code,
            "row_id": row_id,
            "filename": filename,
            "version": version,
            "student_name": normalize_text(row["Hallgató neve"]),
            "supervisor_name": normalize_text(row["Konzulens neve"]),
            "degree": normalize_text(row["Képzés"]),
            "faculty": normalize_text(row["Szak"]),
            "subject": normalize_text(row["Tantárgy"]),
            "title_hu": normalize_text(row["Téma magyar címe"]),
            "title_en": normalize_text(row["Téma angol címe"]),
            "download_url": url,
            "should_download": normalize_text(row["Feladatkiírás státusza"])
            == "Feltöltve, tanszékvezetői jóváhagyásra vár",
        })

    workbook.close()
    return records


def ensure_schema(connection):
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS "import" (
            neptun_code TEXT NOT NULL,
            row_id INTEGER,
            filename TEXT NOT NULL UNIQUE,
            version INTEGER NOT NULL,
            student_name TEXT,
            supervisor_name TEXT,
            degree TEXT,
            faculty TEXT,
            subject TEXT,
            title_hu TEXT,
            title_en TEXT,
            UNIQUE (neptun_code, version)
        );
        CREATE TABLE IF NOT EXISTS "reviews" (
            neptun_code TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT,
            ekovacsG TEXT,
            eGuszti TEXT,
            eGume TEXT,
            ePali TEXT,
            PRIMARY KEY (neptun_code, version)
        );
        """
    )
    ensure_extract_schema(connection)


def ensure_extract_schema(connection):
    column_definitions = ",\n            ".join(
        f'"{column}" {column_type}'
        for column, column_type in EXTRACT_COLUMNS.items()
    )
    connection.execute(
        f'CREATE TABLE IF NOT EXISTS "extract" ('
        f'filename TEXT PRIMARY KEY NOT NULL, {column_definitions})'
    )


def create_compatibility_views(connection):
    connection.execute("DROP VIEW IF EXISTS filtered_dipterv")
    connection.execute("DROP TRIGGER IF EXISTS dipterv_update")
    connection.execute("DROP VIEW IF EXISTS dipterv")
    connection.executescript(
        """
        CREATE VIEW dipterv AS
        SELECT
            i.row_id AS id,
            i.filename,
            i.version AS verzio,
            i.student_name AS hallgato,
            i.supervisor_name AS konzulens,
            i.degree AS szint,
            r.status,
            r.ekovacsG,
            r.eGuszti,
            r.eGume,
            r.ePali,
            i.neptun_code,
            i.faculty,
            i.subject,
            i.title_hu,
            i.title_en,
            e.template_status
        FROM "import" AS i
        LEFT JOIN reviews AS r
          ON r.neptun_code = i.neptun_code AND r.version = i.version
        LEFT JOIN "extract" AS e ON e.filename = i.filename;

        CREATE VIEW filtered_dipterv AS
        SELECT *
        FROM dipterv AS t1
        WHERE t1.status != 'OK'
          AND NOT (
            t1.status = 'OLD'
            AND EXISTS (
              SELECT 1
              FROM dipterv AS t2
              WHERE t2.hallgato = t1.hallgato
                AND t2.konzulens = t1.konzulens
                AND t2.status = 'OK'
            )
          );

        CREATE TRIGGER dipterv_update
        INSTEAD OF UPDATE ON dipterv
        BEGIN
            UPDATE reviews
            SET status = NEW.status,
                ekovacsG = NEW.ekovacsG,
                eGuszti = NEW.eGuszti,
                eGume = NEW.eGume,
                ePali = NEW.ePali
            WHERE neptun_code = OLD.neptun_code AND version = OLD.verzio;
        END;
        """
    )


def sync_import_records(records, database_path=DATABASE_PATH):
    connection = sqlite3.connect(database_path)
    try:
        ensure_schema(connection)
        connection.execute("BEGIN")
        for record in records:
            values = tuple(record[column] for column in IMPORT_COLUMNS)
            current = connection.execute(
                'SELECT * FROM "import" WHERE (neptun_code = ? AND version = ?) OR filename = ? '
                'ORDER BY CASE WHEN neptun_code = ? AND version = ? THEN 0 ELSE 1 END LIMIT 1',
                (record["neptun_code"], record["version"], record["filename"], record["neptun_code"], record["version"]),
            ).fetchone()

            if current is None:
                placeholders = ", ".join("?" for _ in IMPORT_COLUMNS)
                columns = ", ".join(IMPORT_COLUMNS)
                connection.execute(
                    f'INSERT INTO "import" ({columns}) VALUES ({placeholders})', values
                )
                print(
                    f"Added import record: row {record['row_id']}, "
                    f"version {record['version']}, {record['filename']}"
                )
            else:
                missing = []
                changed = []
                for column, new_value in zip(IMPORT_COLUMNS, values):
                    old_value = current[column]
                    if old_value != new_value:
                        if old_value in (None, "") and new_value not in (None, ""):
                            missing.append(column)
                        else:
                            changed.append(column)
                if missing:
                    print(
                        f"Added missing import data for {record['neptun_code']} "
                        f"version {record['version']}: {', '.join(missing)}"
                    )
                if changed:
                    print(
                        f"WARNING: Import data differs for {record['neptun_code']} "
                        f"version {record['version']}; overwriting: {', '.join(changed)}"
                    )
                assignments = ", ".join(f"{column} = ?" for column in IMPORT_COLUMNS)
                connection.execute(
                    f'UPDATE "import" SET {assignments} WHERE neptun_code = ? AND version = ?',
                    values + (current["neptun_code"], current["version"]),
                )
                if (current["neptun_code"], current["version"]) != (record["neptun_code"], record["version"]):
                    connection.execute(
                        "UPDATE reviews SET neptun_code = ?, version = ? WHERE neptun_code = ? AND version = ?",
                        (record["neptun_code"], record["version"], current["neptun_code"], current["version"]),
                    )

            connection.execute(
                "INSERT OR IGNORE INTO reviews (neptun_code, version) VALUES (?, ?)",
                (record["neptun_code"], record["version"]),
            )

        create_compatibility_views(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: create_db.py <workbook.xlsx>")
    records = load_import_rows(sys.argv[1])
    sync_import_records(records)


if __name__ == "__main__":
    main()