import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team = json.loads(row[0])

participants = team['config']['participants']
for p in participants:
    pname = p['config']['name']
    tools = p['config'].get('workbench', {}).get('config', {}).get('tools', [])
    for tool in tools:
        tname = tool['config'].get('name', 'N/A')
        src = tool['config'].get('source_code', '')
        print(f"Agent={pname}, Tool={tname}")
        print(f"  Source starts with: {src[:100]!r}")
        print(f"  Has pymupdf4llm: {'pymupdf4llm' in src}")
        print()

conn.close()
