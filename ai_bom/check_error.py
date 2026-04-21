import sqlite3, json
conn = sqlite3.connect(r"C:\Users\info\.autogenstudio\autogen04202.db")
row = conn.execute("SELECT id, status, error_message, task, team_result, messages FROM run ORDER BY id DESC LIMIT 1").fetchone()
print("RUN ID:", row[0])
print("STATUS:", row[1])
print("\n=== ERROR ===")
print(row[2])
print("\n=== TASK ===")
try:
    print(json.dumps(json.loads(row[3]), indent=2))
except:
    print(row[3])
print("\n=== TEAM RESULT ===")
try:
    print(json.dumps(json.loads(row[4]), indent=2))
except:
    print(row[4])
print("\n=== MESSAGES ===")
try:
    msgs = json.loads(row[5] or "[]")
    for m in msgs:
        print(json.dumps(m, indent=2))
except:
    print(row[5])

# Also check message table for this run
print("\n=== MESSAGE TABLE ===")
msgs2 = conn.execute("SELECT id, config FROM message WHERE run_id=? ORDER BY id", (row[0],)).fetchall()
for m in msgs2:
    try:
        c = json.loads(m[1])
        print(f"[{m[0]}] source={c.get('source')} type={c.get('type')}")
        content = c.get('content')
        if isinstance(content, str):
            print("  content:", content[:500])
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    print("  item:", json.dumps(item)[:500])
    except:
        print(m[1][:300])
conn.close()
