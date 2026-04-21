import sqlite3, json

conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur.fetchall()])

# Find tools in team id=4
cur.execute("SELECT component FROM team WHERE id=4")
row = cur.fetchone()
data = json.loads(row[0])

# Look for tools in participants
for p in data['config']['participants']:
    name = p['config']['name']
    tools = p['config'].get('tools', [])
    print(f"\nAgent: {name} — {len(tools)} tools")
    for t in tools:
        label = t.get('label', t.get('name', '?'))
        src = t.get('config', {}).get('source_code', '')
        print(f"  Tool: {label} ({len(src)} chars)")
        if 'extract_pdf' in label.lower() or 'extract_pdf' in src[:200].lower():
            print("    *** FOUND extract_pdf_data ***")
            # Print first 300 chars
            print("    Preview:", src[:300])

conn.close()
