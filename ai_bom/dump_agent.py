import sqlite3, json

conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
row = cur.fetchone()
data = json.loads(row[0])
conn.close()

# Dump first participant fully to understand structure
p = data['config']['participants'][0]
print(json.dumps(p, indent=2)[:3000])
