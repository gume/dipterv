#!/usr/bin/env python3
# Deletes extract rows with template_status > 0 so extract_docs.py re-extracts them.
import sqlite3
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/db/descriptions.sqlite"
c = sqlite3.connect(path)
cur = c.execute('DELETE FROM "extract" WHERE template_status > 0')
c.commit()
print(f"Deleted {cur.rowcount} extract rows.")
