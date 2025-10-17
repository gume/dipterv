import sqlite3
from collections import defaultdict

conn = sqlite3.connect("/db/descriptions.sqlite")
cursor = conn.cursor()

# Fetch all rows with status 'Not OK', sorted by konzulens and hallgato
cursor.execute("""
    SELECT hallgato, konzulens, filename, status, eKovacsG, eGuszti
    FROM dipterv
    WHERE status = 'Not OK'
    ORDER BY konzulens, hallgato;
""")
rows = cursor.fetchall()
conn.close()

# Group by konzulens
grouped = defaultdict(list)
for hallgato, konzulens, filename, status, review1, review2 in rows:
    grouped[konzulens].append((hallgato, filename, status, review1, review2))

# Print grouped output
for konzulens in sorted(grouped):
    print(f"\nKonzulens: {konzulens}")
    for hallgato, filename, status, review1, review2 in grouped[konzulens]:
        print(f"Hallgató: {hallgato}\nReview1: {review1}\nReview2: {review2}\n\n")
    print("-----")