import sqlite3, json
conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute('SELECT id, user_id, component FROM team')
for row in cur.fetchall():
    comp = json.loads(row[2])
    print(f"  id={row[0]}  user={row[1]}  label={comp.get('label','?')}")
conn.close()
