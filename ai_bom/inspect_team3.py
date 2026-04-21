import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team = json.loads(row[0])

print("Top-level keys:", list(team.keys()))
config = team.get('config', {})
print("Config keys:", list(config.keys()))

# Look for reflect_on_tool_use in the whole JSON
full_str = json.dumps(team)
if 'reflect' in full_str:
    idx = full_str.find('reflect')
    print("\nFound 'reflect' at index", idx)
    print("Context:", full_str[max(0,idx-100):idx+200])
else:
    print("\nNo 'reflect' found in team JSON")

# Print config structure
print("\nConfig structure (first 2000 chars):")
print(json.dumps(config, indent=2)[:2000])
conn.close()
