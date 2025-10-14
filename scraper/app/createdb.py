#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import re
import sqlite3
import pandas as pd

cnx = sqlite3.connect('/db/descriptions.sqlite')
cursor = cnx.cursor()

init_db = 'CREATE TABLE IF NOT EXISTS "dipterv" ("id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,"filename" VARCHAR, "hallgato" VARCHAR, "konzulens" VARCHAR, "szint" VARCHAR, "ekovacsG" VARCHAR, "eGuszti" VARCHAR, "eGume" VARCHAR, "ePali" VARCHAR)'
cursor.execute(init_db)

df = pd.read_excel(sys.argv[1], skiprows=3)
for index, row in df.iterrows():
    filename = ""
    st = row[u'Feladatkiírás státusza']
    if st == u'Feltöltve, tanszékvezetői jóváhagyásra vár' or st == u'Nincs beadva, mert a tanszékvezető nem hagyta jóvá':
        rf = re.search('Theses/(.*)/', row[u'Téma oktatói szerkesztő oldalának címe (URL) a portálon'])
        if (rf != None):
            filename = rf.group(1)
        hallgato = row[u'Hallgató neve']
        konzulens = row[u'Konzulens neve']
        szint = row[u'Képzés']
        data_row = (str(index), filename, hallgato.encode('utf-8'), konzulens.encode('utf-8'), szint.encode('utf-8'))
        print (f"{data_row[0]}, {data_row[1]}, {data_row[2]}, {data_row[3]}, {data_row[4]}")
        add_row = ("INSERT INTO dipterv "
            "(id, filename, hallgato, konzulens, szint) "
            "VALUES (?, ?, ?, ?, ?);")
        data_row = (str(index), filename, hallgato.encode('utf-8'), konzulens.encode('utf-8'), szint.encode('utf-8'))
        cursor.execute (add_row, data_row);

cnx.commit()

cursor.close()
cnx.close()
