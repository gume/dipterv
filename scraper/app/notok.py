import sqlite3
from collections import defaultdict

conn = sqlite3.connect("/db/descriptions.sqlite")
conn.row_factory = sqlite3.Row

# Descriptions with a "nogo" verdict, grouped by supervisor, with the human remarks.
rows = conn.execute("""
    SELECT i.neptun_code, i.version, i.student_name, i.supervisor_name, i.filename
    FROM "import" AS i
    JOIN review_verdict AS v ON v.neptun_code = i.neptun_code AND v.version = i.version
    WHERE v.status = 'nogo'
    ORDER BY i.supervisor_name, i.student_name
""").fetchall()

grouped = defaultdict(list)
for row in rows:
    remarks = conn.execute("""
        SELECT COALESCE(p.name, r.reviewer) AS reviewer, r.result
        FROM reviews AS r
        LEFT JOIN reviewers AS p ON p.id = r.reviewer
        WHERE r.neptun_code = ? AND r.version = ? AND r.aspect = 'remark'
        ORDER BY p.rowid, r.reviewer
    """, (row["neptun_code"], row["version"])).fetchall()
    grouped[row["supervisor_name"]].append((row, remarks))
conn.close()

for supervisor in sorted(grouped, key=lambda name: name or ""):
    print(f"\nKonzulens: {supervisor}")
    for row, remarks in grouped[supervisor]:
        print(f"Hallgató: {row['student_name']} (v{row['version']})\n")
        for remark in remarks:
            if remark["result"]:
                print(f"{remark['reviewer']}: {remark['result']}\n")
        print("\n")
    print("-----")
