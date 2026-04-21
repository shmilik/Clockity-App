import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT id, component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team_id, component_json = row
team = json.loads(component_json)

# Find and fix all reflect_on_tool_use occurrences
full_str = json.dumps(team)
count = full_str.count('"reflect_on_tool_use": true')
print(f"Found {count} agents with reflect_on_tool_use = true")

# Navigate the participants
participants = team['config']['participants']
print(f"Number of participants: {len(participants)}")

for i, p in enumerate(participants):
    name = p['config']['name']
    reflect = p['config'].get('reflect_on_tool_use', False)
    print(f"Agent {i}: {name}, reflect_on_tool_use = {reflect}")
    if reflect:
        print(f"  -> Setting to False")
        p['config']['reflect_on_tool_use'] = False

# Save
updated_json = json.dumps(team)
c.execute('UPDATE team SET component = ? WHERE id = ?', (updated_json, team_id))
conn.commit()
print("\nDone! Saved to database.")
conn.close()
