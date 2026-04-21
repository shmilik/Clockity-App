import sqlite3, json

conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])
conn.close()

for p in data['config']['participants']:
    if p['config']['name'] == 'bom_calculator':
        tools = p['config']['workbench']['config']['tools']
        for t in tools:
            if 'calculate_solar_bom' in t['config']['source_code'][:100]:
                print(t['config']['source_code'])
