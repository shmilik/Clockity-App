import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT id, component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
if not row:
    print('Team not found!')
    conn.close()
    exit()

team_id, component_json = row
team = json.loads(component_json)
print('Team found, ID:', team_id)

# Fix bom_calculator agent - set reflect_on_tool_use to False
agents = team.get('component', {}).get('participants', [])
found = False
for agent in agents:
    name = agent.get('component', {}).get('name', '')
    print(f'Agent: {name}')
    if 'calculator' in name.lower() or 'bom' in name.lower():
        found = True
        comp = agent.get('component', {})
        print(f'  Keys: {list(comp.keys())}')
        if 'reflect_on_tool_use' in comp:
            print(f'  reflect_on_tool_use before: {comp["reflect_on_tool_use"]}')
            comp['reflect_on_tool_use'] = False
            print(f'  reflect_on_tool_use after: {comp["reflect_on_tool_use"]}')
        else:
            print('  reflect_on_tool_use key not in top-level component keys')
            # Maybe it's nested differently
            for k, v in comp.items():
                if 'reflect' in str(k).lower():
                    print(f'  Found reflect key: {k} = {v}')

if not found:
    print('bom_calculator agent not found by name! All agent names:')
    for agent in agents:
        print(' -', agent.get('component', {}).get('name', 'NO NAME'))

print()
updated_json = json.dumps(team)
c.execute('UPDATE team SET component = ? WHERE id = ?', (updated_json, team_id))
conn.commit()
print('Saved!')
conn.close()
