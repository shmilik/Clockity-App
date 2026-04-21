import sqlite3, json

DB = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data['config']['participants']:
    if p['config']['name'] == 'bom_calculator':
        for t in p['config']['workbench']['config']['tools']:
            src = t['config']['source_code']
            if 'calculate_solar_bom' not in src[:100]:
                continue

            old = (
                '            {"description": "Q.CELLS AC Daisy-Chain Cable (module-to-module, 1 per inter-module gap)",\n'
                '             "part_number": "QCELLS-ACCABLE", "qty": total_inverters - num_rows, "unit": "EA"},'
            )
            new = (
                '            {"description": "Q.CELLS AC Daisy-Chain Cable (module-to-module, 1 per panel)",\n'
                '             "part_number": "QCELLS-ACCABLE", "qty": total_inverters, "unit": "EA"},'
            )
            if old in src:
                src = src.replace(old, new)
                print("✓ Q.CELLS AC cable qty changed to 1 per panel")
            else:
                print("ERROR: Could not find the cable line — check source")

            t['config']['source_code'] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
