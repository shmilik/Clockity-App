import sqlite3, json
db = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT id, status, task_result FROM run WHERE id=21")
row = cur.fetchone()
print("Run id:", row[0], "Status:", row[1])
result = json.loads(row[2])
print("\ntask_result keys:", list(result.keys()))
tr = result.get('task_result', {})
print("task_result sub-keys:", list(tr.keys()) if isinstance(tr, dict) else type(tr))
msgs = tr.get('messages', []) if isinstance(tr, dict) else []
print("\nMessages:")
for m in msgs:
    print(f"  source={m.get('source')} type={m.get('type')} content={str(m.get('content',''))[:200]}")
err = result.get('error', tr.get('error', ''))
print("\nError:", err)
conn.close()
