import sqlite3, json

conn = sqlite3.connect("C:/Users/info/.autogenstudio/autogen04202.db")
cur = conn.cursor()
cur.execute("SELECT messages FROM run ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
conn.close()

msgs = json.loads(row[0])
print(f"Total messages: {len(msgs)}")
for m in msgs:
    src = m.get("source", "")
    content = m.get("content", "")
    if isinstance(content, list):
        content = str(content)
    content = str(content)
    # Print last few messages and any that mention errors or sheets
    if any(k in content.lower() for k in ["error", "failed", "google", "sheet", "url", "http", "bom_sheets", "xlsx"]):
        print(f"\n[{src}]: {content[:1000]}")

print("\n--- LAST 3 MESSAGES ---")
for m in msgs[-3:]:
    src = m.get("source", "")
    content = str(m.get("content", ""))
    print(f"[{src}]: {content[:600]}")
