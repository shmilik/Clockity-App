import sqlite3, json
conn = sqlite3.connect(r'C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute("SELECT id, team_id, status, error_message FROM run ORDER BY id DESC LIMIT 5")
for row in cur.fetchall():
    print(f"run_id={row[0]} team={row[1]} status={row[2]}")
    if row[3]:
        print(f"  ERROR: {row[3][:800]}")
conn.close()
