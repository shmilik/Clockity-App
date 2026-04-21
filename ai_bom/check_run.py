import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get latest run messages
c.execute("SELECT id, status, error_message FROM run ORDER BY created_at DESC LIMIT 1")
run = c.fetchone()
run_id, status, err = run
print(f"Latest run ID: {run_id}, Status: {status}")
if err:
    print(f"Error: {err[:500]}")

# Get all messages for this run
c.execute("SELECT messages FROM run WHERE id = ?", (run_id,))
row = c.fetchone()
if row and row[0]:
    try:
        msgs = json.loads(row[0])
        print(f"\nTotal messages: {len(msgs)}")
        for i, m in enumerate(msgs):
            src = m.get('source', '?')
            mtype = m.get('type', '?')
            content = m.get('content', '')
            if isinstance(content, str):
                preview = content[:300]
            elif isinstance(content, list):
                preview = str(content)[:300]
            else:
                preview = str(content)[:300]
            print(f"\n[{i}] {src} ({mtype}):")
            print(f"  {preview}")
    except Exception as e:
        print(f"Could not parse messages: {e}")

conn.close()
