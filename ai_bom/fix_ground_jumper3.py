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

            # Find exact splice point: right before the closing of qcells_integrated list
            # We'll insert the new item just before the `]\n    elif`
            MARKER = '        ]\n    elif inv_sys == "enphase_iq":'
            JUMPER_LINE = (
                '            {"description": \'Module Ground Jumper 8" (1 per row + 1 per row break)\',\n'
                '             "part_number": "4011011", "qty": num_rows + max(row_breaks, 0), "unit": "EA"},\n'
            )

            # Find position of MARKER after the qcells_integrated block
            qcells_idx = src.find('if inv_sys == "qcells_integrated"')
            marker_idx = src.find(MARKER, qcells_idx)

            if marker_idx == -1:
                print("ERROR: Could not find closing marker")
                print("Nearby:", repr(src[qcells_idx:qcells_idx+600]))
            else:
                # Insert the jumper line before the closing ]
                src = src[:marker_idx] + JUMPER_LINE + src[marker_idx:]
                print("✓ Module Ground Jumper inserted")

            t['config']['source_code'] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
