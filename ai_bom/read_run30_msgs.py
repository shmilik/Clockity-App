import sqlite3, json
conn = sqlite3.connect(r'C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
# Get last complete run's messages
cur.execute("SELECT messages FROM run WHERE id=30")
row = cur.fetchone()
conn.close()
msgs = json.loads(row[0]) if row[0] else []
if isinstance(msgs, list):
    for m in msgs:
        src = m.get('source','?')
        content = m.get('content','')
        if isinstance(content, list):
            for c in content:
                text = c.get('text','') or c.get('content','')
                if text and len(text) > 30:
                    print(f"\n[{src}]:\n{text[:1200]}")
        elif isinstance(content, str) and len(content) > 30:
            print(f"\n[{src}]:\n{content[:1200]}")
