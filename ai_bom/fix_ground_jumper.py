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

            # Add Module Ground Jumper to qcells_integrated cable_bom
            old = (
                '    if inv_sys == "qcells_integrated":\n'
                '        cable_bom = [\n'
                '            {"description": "Q.CELLS AC Daisy-Chain Cable (module-to-module, 1 per panel)",\n'
                '             "part_number": "QCELLS-ACCABLE", "qty": total_inverters, "unit": "EA"},\n'
                '            {"description": "Q.CELLS Branch Circuit End Cap / Terminator",  \n'
                '             "part_number": "QCELLS-TERMCAP", "qty": num_rows * 2,          \n    "unit": "EA"}, \n'
                '            {"description": "Q.CELLS Combiner Branch Leads (1 per string/row)",\n'
                '             "part_number": "QCELLS-LEAD",    "qty": num_rows,              \n    "unit": "EA"}, \n'
                '        ]'
            )
            new = (
                '    if inv_sys == "qcells_integrated":\n'
                '        cable_bom = [\n'
                '            {"description": "Q.CELLS AC Daisy-Chain Cable (module-to-module, 1 per panel)",\n'
                '             "part_number": "QCELLS-ACCABLE", "qty": total_inverters, "unit": "EA"},\n'
                '            {"description": "Q.CELLS Branch Circuit End Cap / Terminator",  \n'
                '             "part_number": "QCELLS-TERMCAP", "qty": num_rows * 2,          \n    "unit": "EA"}, \n'
                '            {"description": "Q.CELLS Combiner Branch Leads (1 per string/row)",\n'
                '             "part_number": "QCELLS-LEAD",    "qty": num_rows,              \n    "unit": "EA"}, \n'
                '            {"description": "Module Ground Jumper 8\\" (1 per row + 1 per row break)",\n'
                '             "part_number": "4011011", "qty": num_rows + max(row_breaks, 0), "unit": "EA"},\n'
                '        ]'
            )

            if old in src:
                src = src.replace(old, new)
                print("✓ Module Ground Jumper added to qcells_integrated BOM")
            else:
                print("ERROR: Could not find qcells_integrated cable_bom block")
                # Print a snippet to debug
                idx = src.find('qcells_integrated')
                print("Nearby:", repr(src[idx:idx+400]))

            t['config']['source_code'] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
