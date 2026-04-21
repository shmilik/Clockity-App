import sqlite3, json
db=r'C:\Users\info\.autogenstudio\autogen04202.db'
c=sqlite3.connect(db).cursor()
c.execute('SELECT component FROM team WHERE id=4')
d=json.loads(c.fetchone()[0])
for p in d['config']['participants']:
    if p['config']['name']!='bom_calculator': continue
    for t in p['config'].get('workbench',{}).get('config',{}).get('tools',[]):
        if t['config']['name']=='calculate_solar_bom':
            src=t['config']['source_code']
g={'json':json}
exec(src,g)
fn=g['calculate_solar_bom']

def check(label, **kw):
    r=json.loads(fn(**kw))
    items={i['part_number']:i['qty'] for i in r['bom']}
    print(f'{label}:')
    print(f'  Mids={items.get("CLM-0003B",0)}  Ends={items.get("CLM-0002B",0)}  Lugs={items.get("GR-LUG-100",0)}')

# User's reported correct: 84 mids, 40 ends
# Needs: panel_count=48, num_rows_override=6, row_breaks=4
check('User job (48 panels, 6 rows, 4 breaks)',
      panel_count=48, panel_orientation='portrait', panels_per_row=8,
      num_rows_override=6, row_breaks=4)

# AI was extracting ppr=11, nr=6, rb=0 -> gave 120/24
# Simulate that scenario with old-style params (no override)
check('Old AI extraction (ppr=11, 6 rows derived, 0 breaks)',
      panel_count=66, panel_orientation='portrait', panels_per_row=11,
      row_breaks=0)

# Correct extraction for that same job if panel_count right
check('Corrected (66 panels, nr_override=6, 4 breaks)',
      panel_count=66, panel_orientation='portrait', panels_per_row=11,
      num_rows_override=6, row_breaks=4)
