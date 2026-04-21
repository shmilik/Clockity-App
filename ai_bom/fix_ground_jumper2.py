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
                '            {"description": "Q.CELLS Combiner Branch Leads (1 per string/row)",\n'
                '             "part_number": "QCELLS-LEAD",    "qty": num_rows,                \n  "unit": "EA"},\n'
                '        ]\n'
                '    elif inv_sys == "enphase_iq":'
            )
            new = (
                '            {"description": "Q.CELLS Combiner Branch Leads (1 per string/row)",\n'
                '             "part_number": "QCELLS-LEAD",    "qty": num_rows,                \n  "unit": "EA"},\n'
                '            {"description": \'Module Ground Jumper 8" (1 per row + 1 per row break)\',\n'
                '             "part_number": "4011011", "qty": num_rows + max(row_breaks, 0), "unit": "EA"},\n'
                '        ]\n'
                '    elif inv_sys == "enphase_iq":'
            )

            if old in src:
                src = src.replace(old, new)
                print("✓ Module Ground Jumper added")
            else:
                print("ERROR: Still no match — printing exact bytes around LEAD line")
                idx = src.find('QCELLS-LEAD')
                print(repr(src[idx-10:idx+200]))

            t['config']['source_code'] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
