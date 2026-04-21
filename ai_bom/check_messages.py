import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get the message table messages for run 14
c.execute("PRAGMA table_info(message)")
cols = [col[1] for col in c.fetchall()]
print("Message table columns:", cols)

c.execute("SELECT * FROM message WHERE run_id = 14 ORDER BY id")
rows = c.fetchall()
print(f"\nFound {len(rows)} messages in message table for run 14")
for row in rows:
    d = dict(zip(cols, row))
    src = d.get('source', '?')
    content = d.get('content', '')
    if isinstance(content, str):
        preview = content[:400]
    print(f"\n[{d.get('id')}] {src}:")
    print(f"  {preview}")

conn.close()
