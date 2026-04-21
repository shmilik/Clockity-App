import sqlite3, json
conn = sqlite3.connect(r'C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute("SELECT messages FROM run WHERE id=30")
row = cur.fetchone()
conn.close()
raw = row[0]
print(type(raw), repr(raw[:200]) if raw else "NULL")
