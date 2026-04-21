import sqlite3, json
db = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("PRAGMA table_info(run)")
cols = [r[1] for r in cur.fetchall()]
print("Run columns:", cols)
cur.execute("SELECT * FROM run WHERE id=21")
row = cur.fetchone()
for col, val in zip(cols, row):
    print(f"\n{col}: {str(val)[:500]}")
conn.close()
