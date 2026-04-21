import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team = json.loads(row[0])
participants = team.get('component', {}).get('participants', [])
print(f'Number of participants: {len(participants)}')
for i, p in enumerate(participants):
    comp = p.get('component', {})
    name = comp.get('name', 'N/A')
    ctype = comp.get('component_type', 'N/A')
    print(f'Participant {i}: name={name}, type={ctype}')
    full_str = json.dumps(comp)
    if 'reflect' in full_str.lower():
        print(f'  HAS reflect_on_tool_use in JSON')
        # Find exact location
        for k, v in comp.items():
            if 'reflect' in k.lower():
                print(f'  Key: {k} = {v}')
conn.close()
