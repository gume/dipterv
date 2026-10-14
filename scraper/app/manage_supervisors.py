#!/usr/bin/env python3
"""Manage the supervisor logins and settings used by the read-only supervisor web container.

The supervisors table is filled from the portal workbook by create_db.py.
"""

import argparse
import sqlite3
import sys

from create_db import ensure_supervisor_schema

DEFAULT_DATABASE = "/db/descriptions.sqlite"
AI_MODEL_KEY = "supervisor_ai_model"


def ensure_tables(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS "supervisors" (
            neptun_code TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            alt_name TEXT
        );
        CREATE TABLE IF NOT EXISTS "settings" (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT
        );
        """
    )
    ensure_supervisor_schema(connection)


def list_supervisors(connection):
    rows = connection.execute(
        """
        SELECT s.neptun_code, s.name, s.alt_name,
               (SELECT COUNT(*) FROM "import" AS i WHERE i.supervisor_code = s.neptun_code)
        FROM supervisors AS s
        ORDER BY COALESCE(NULLIF(s.alt_name, ''), s.name)
        """
    ).fetchall()
    print(f"{'Neptun':8}  {'Descr.':>6}  Name (alternative name used when set)")
    for neptun, name, alt_name, count in rows:
        shown = f"{alt_name}  [portal: {name}]" if alt_name else name
        print(f"{neptun:8}  {count:>6}  {shown}")
    model = connection.execute('SELECT value FROM settings WHERE key = ?', (AI_MODEL_KEY,)).fetchone()
    print(f"\nAI model shown to supervisors: {model[0] if model and model[0] else '(not set)'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--list", action="store_true", help="List supervisors with their description counts.")
    parser.add_argument("--add", nargs=2, metavar=("NEPTUN", "NAME"),
                        help="Create or update a supervisor by hand; NAME is the portal name.")
    parser.add_argument("--alt-name", nargs=2, metavar=("NEPTUN", "NAME"),
                        help="Set the name shown instead of the portal name; an empty NAME clears it.")
    parser.add_argument("--remove", metavar="NEPTUN", help="Delete a supervisor.")
    parser.add_argument("--ai-model", metavar="MODEL",
                        help="Reviewer id of the AI model whose review supervisors see.")
    args = parser.parse_args(argv)

    connection = sqlite3.connect(args.database)
    try:
        ensure_tables(connection)
        if args.add:
            neptun, name = args.add[0].strip().upper(), args.add[1].strip()
            connection.execute(
                'INSERT INTO supervisors (neptun_code, name) VALUES (?, ?) '
                'ON CONFLICT(neptun_code) DO UPDATE SET name = excluded.name',
                (neptun, name),
            )
            print(f"Saved {neptun} -> {name}.")
        if args.alt_name:
            neptun, alt = args.alt_name[0].strip().upper(), args.alt_name[1].strip()
            updated = connection.execute(
                'UPDATE supervisors SET alt_name = ? WHERE neptun_code = ?', (alt or None, neptun)
            ).rowcount
            if not updated:
                print(f"ERROR: unknown supervisor {neptun}.", file=sys.stderr)
                return 1
            print(f"Alternative name of {neptun}: {alt or '(cleared)'}")
        if args.remove:
            deleted = connection.execute(
                'DELETE FROM supervisors WHERE neptun_code = ?', (args.remove.strip().upper(),)
            ).rowcount
            print(f"Removed {deleted} supervisor.")
        if args.ai_model:
            connection.execute(
                'INSERT INTO settings (key, value) VALUES (?, ?) '
                'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                (AI_MODEL_KEY, args.ai_model),
            )
            print(f"AI model for supervisors: {args.ai_model}")
        connection.commit()
        if args.list or not (args.add or args.alt_name or args.remove or args.ai_model):
            list_supervisors(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
