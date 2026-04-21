import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT id, component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team_id, component_json = row
team = json.loads(component_json)

participants = team['config']['participants']
for p in participants:
    pname = p['config']['name']
    sys_prompt = p['config'].get('system_message', 'N/A')
    print(f"=== {pname} ===")
    print(sys_prompt[:500])
    print()

conn.close()
