import sqlite3, json

conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
row = cur.fetchone()
data = json.loads(row[0])
conn.close()

# Get extract_pdf_data source from pdf_extractor agent (participant 0, tool 0)
p0 = data['config']['participants'][0]
tools = p0['config']['workbench']['config']['tools']
print(f"pdf_extractor has {len(tools)} tools")
for i, t in enumerate(tools):
    print(f"  Tool {i}: {t.get('label','?')} — {t.get('description','')[:80]}")
    src = t['config']['source_code']
    print(f"  Source length: {len(src)}")

# Print full source of first tool
print("\n\n=== FULL SOURCE ===")
print(tools[0]['config']['source_code'])
