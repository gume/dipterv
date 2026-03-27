import sqlite3
from collections import defaultdict

conn = sqlite3.connect("/db/descriptions.sqlite")
cursor = conn.cursor()

# Fetch all rows with status 'Not OK', sorted by konzulens and hallgato
cursor.execute("""
    SELECT hallgato, konzulens, filename, status, eKovacsG, eGuszti, eGume, ePali
    FROM dipterv
    WHERE status = 'Not OK'
    ORDER BY konzulens, hallgato;
""")
rows = cursor.fetchall()
conn.close()

# Group by konzulens
grouped = defaultdict(list)
for hallgato, konzulens, filename, status, review1, review2, review3, review4 in rows:
    grouped[konzulens].append((hallgato, filename, status, review1, review2, review3, review4))

# Print grouped output
for konzulens in sorted(grouped):
    print(f"\nKonzulens: {konzulens}")
    for hallgato, filename, status, review1, review2, review3, review4 in grouped[konzulens]:
        print(f"Hallgató: {hallgato}\n")
        if review1:
            print(f"Review1: {review1}\n")
        if review2:
            print(f"Review2: {review2}\n")
        if review3:
            print(f"Review3: {review3}\n")
        if review4:
            print(f"Review4: {review4}\n")
        print("\n")
    print("-----")