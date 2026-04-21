import sqlite3, json
db = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)
for t in tables:
    if any(x in t.lower() for x in ['run', 'session', 'message', 'error']):
        try:
            cur.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 2")
            rows = cur.fetchall()
            if rows:
                print(f"\n--- {t} ---")
                for r in rows:
                    print(str(r)[:400])
        except Exception as e:
            print(f"{t}: {e}")
conn.close()
