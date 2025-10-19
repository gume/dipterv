#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import re
import sqlite3
import pandas as pd
import os
import glob

cnx = sqlite3.connect('/db/descriptions.sqlite')
cursor = cnx.cursor()

#init_db = 'CREATE TABLE IF NOT EXISTS "dipterv" ("id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,"filename" VARCHAR, "hallgato" VARCHAR, "konzulens" VARCHAR, "szint" VARCHAR, "ekovacsG" VARCHAR, "eGuszti" VARCHAR, "eGume" VARCHAR, "ePali" VARCHAR)'
init_db = """
CREATE TABLE IF NOT EXISTS dipterv (
    id INTEGER,
    filename VARCHAR PRIMARY KEY NOT NULL,
    hallgato VARCHAR,
    konzulens VARCHAR,
    szint VARCHAR,
    status VARCHAR,
    ekovacsG VARCHAR,
    eGuszti VARCHAR,
    eGume VARCHAR,
    ePali VARCHAR
)
"""
cursor.execute(init_db)

init_view_db = """
CREATE VIEW IF NOT EXISTS filtered_dipterv AS
SELECT *
FROM dipterv t1
WHERE t1.status != 'OK'
  AND NOT (
    t1.status = 'OLD'
    AND EXISTS (
      SELECT 1
      FROM dipterv t2
      WHERE t2.hallgato = t1.hallgato
        AND t2.konzulens = t1.konzulens
        AND t2.status = 'OK'
    )
  );
"""
cursor.execute(init_view_db)

df = pd.read_excel(sys.argv[1], skiprows=3)
for index, row in df.iterrows():
    filename = ""
    st = row[u'Feladatkiírás státusza']
    if st == u'Feltöltve, tanszékvezetői jóváhagyásra vár' or st == u'Nincs beadva, mert a tanszékvezető nem hagyta jóvá':
        rf = re.search('Theses/(.*)/', row[u'Téma oktatói szerkesztő oldalának címe (URL) a portálon'])
        if (rf != None):
            filename = rf.group(1)
            pattern = f"/data/{filename}-Feladatkiiras-*.pdf"
            files = glob.glob(pattern)
            max_num = 0
            for f in files:
                match = re.search(rf"{re.escape(filename)}-Feladatkiiras-(\d+)\.pdf$", os.path.basename(f))
                if match:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
            filename = f"{filename}-Feladatkiiras-{max_num}.pdf" if max_num > 0 else ""
        hallgato = row[u'Hallgató neve']
        konzulens = row[u'Konzulens neve']
        szint = row[u'Képzés']
        print (f"{index}, {filename}, {hallgato}, {konzulens}, {szint}")

        # UPSERT: replace existing row with same id (or insert new)
        add_row = ("INSERT OR REPLACE INTO dipterv "
                   "(id, filename, hallgato, konzulens, szint) "
                   "VALUES (?, ?, ?, ?, ?);")
        # use plain strings (no .encode)
        data_row = (int(index), filename, str(hallgato), str(konzulens), str(szint))
        cursor.execute(add_row, data_row)

        # Extract base name and number from filename
        match = re.match(r"(.+)-(\d+)\.pdf$", filename)
        if match:
            base_name = match.group(1)
            current_num = int(match.group(2))

            # Find all filenames with the same base name
            cursor.execute("SELECT filename, status FROM dipterv WHERE filename LIKE ? AND (status NOT IN ('OK', 'OLD') OR status IS NULL)", (f"{base_name}-%",))
            rows = cursor.fetchall()
            print(f"Found {len(rows)} entries for base name {base_name}")
            if len(rows) >= 2:

                # Find the highest X
                max_num = current_num
                max_filename = filename
                for fname, status in rows:
                    m = re.match(rf"{re.escape(base_name)}-(\d+)\.pdf$", fname)
                    if m:
                        num = int(m.group(1))
                        if num > max_num:
                            max_num = num
                            max_filename = fname
                print(f"Updating statuses for base name {base_name}, keeping {max_filename} as NEW")

                # Set all matching rows to OLD except the highest, which is NEW
                for fname, status in rows:
                    m = re.match(rf"{re.escape(base_name)}-(\d+)\.pdf$", fname)
                    if m:
                        num = int(m.group(1))
                        new_status = "NEW" if fname == max_filename else "OLD"
                        cursor.execute("UPDATE dipterv SET status=? WHERE filename=?", (new_status, fname))

cnx.commit()

cursor.close()
cnx.close()
