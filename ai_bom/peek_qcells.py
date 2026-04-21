import sqlite3, json

DB = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])
conn.close()

for p in data['config']['participants']:
    if p['config']['name'] == 'bom_calculator':
        for t in p['config']['workbench']['config']['tools']:
            src = t['config']['source_code']
            if 'calculate_solar_bom' not in src[:100]:
                continue
            idx = src.find('if inv_sys == "qcells_integrated"')
            print(repr(src[idx:idx+700]))
