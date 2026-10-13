#!/usr/bin/env python3
"""List reviewers in the review tables, or remove one reviewer (e.g. a model) from all of them."""

import argparse
import sqlite3
import sys

from create_db import DATABASE_PATH

# Tables holding a `reviewer` column; review_verdict is not per reviewer.
REVIEWER_TABLES = ("reviews", "review_summaries")


def list_reviewers(connection):
	known = {row[0] for row in connection.execute("SELECT id FROM reviewers")}
	stats = {}
	for row in connection.execute(
		"SELECT reviewer, COUNT(*) AS rows_, COUNT(DISTINCT neptun_code || '|' || version) AS docs, AVG(score) "
		"FROM reviews GROUP BY reviewer"
	):
		stats[row[0]] = {"rows": row[1], "docs": row[2], "avg": row[3], "summaries": 0}
	for row in connection.execute("SELECT reviewer, COUNT(*) FROM review_summaries GROUP BY reviewer"):
		stats.setdefault(row[0], {"rows": 0, "docs": 0, "avg": None, "summaries": 0})["summaries"] = row[1]

	print(f"{'reviewer':<32} {'kind':<6} {'docs':>5} {'review rows':>11} {'summaries':>9} {'avg score':>9}")
	total = {"docs": 0, "rows": 0, "summaries": 0}
	for reviewer in sorted(stats):
		entry = stats[reviewer]
		avg = f"{entry['avg']:.2f}" if entry["avg"] is not None else "-"
		kind = "human" if reviewer in known else "AI"
		print(f"{reviewer:<32} {kind:<6} {entry['docs']:>5} {entry['rows']:>11} {entry['summaries']:>9} {avg:>9}")
		for key in total:
			total[key] += entry[key]
	print(f"{'total':<32} {'':<6} {total['docs']:>5} {total['rows']:>11} {total['summaries']:>9}")
	return known


def remove_reviewer(connection, reviewer, known, assume_yes, force):
	counts = {
		table: connection.execute(f"SELECT COUNT(*) FROM {table} WHERE reviewer = ?", (reviewer,)).fetchone()[0]
		for table in REVIEWER_TABLES
	}
	if not any(counts.values()):
		print(f"Nothing to remove: no rows for reviewer '{reviewer}'.")
		return 1
	if reviewer in known and not force:
		print(f"ERROR: '{reviewer}' is a human reviewer; use --force to remove it anyway.", file=sys.stderr)
		return 2
	print(f"Will delete for '{reviewer}': " + ", ".join(f"{count} rows from {table}" for table, count in counts.items()))
	if not assume_yes and input("Proceed? [y/N] ").strip().lower() != "y":
		print("Aborted.")
		return 1
	with connection:
		for table in REVIEWER_TABLES:
			connection.execute(f"DELETE FROM {table} WHERE reviewer = ?", (reviewer,))
	print("Removed.")
	return 0


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--database", default=DATABASE_PATH)
	parser.add_argument("--list", action="store_true", help="List reviewers with their review counts and totals.")
	parser.add_argument("--remove", metavar="REVIEWER", help="Remove this reviewer/model from all review tables.")
	parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
	parser.add_argument("--force", action="store_true", help="Allow removing a human reviewer.")
	args = parser.parse_args(argv)
	if not args.list and not args.remove:
		parser.error("give --list and/or --remove REVIEWER")

	connection = sqlite3.connect(args.database)
	try:
		known = set()
		if args.list:
			known = list_reviewers(connection)
		if args.remove:
			if not args.list:
				known = {row[0] for row in connection.execute("SELECT id FROM reviewers")}
			return remove_reviewer(connection, args.remove, known, args.yes, args.force)
		return 0
	finally:
		connection.close()


if __name__ == "__main__":
	raise SystemExit(main())
