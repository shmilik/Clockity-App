import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team = json.loads(row[0])

print("Top-level keys:", list(team.keys()))
comp = team.get('component', {})
print("Component keys:", list(comp.keys()))

# Print first 3000 chars of component to understand structure
print("\nFull component (first 3000 chars):")
print(json.dumps(comp, indent=2)[:3000])
conn.close()
