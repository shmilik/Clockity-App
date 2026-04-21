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

print('=== 4 rows of 11, 1 row_break ===')
r=json.loads(fn(panel_count=44,panel_orientation='portrait',panels_per_row=11,num_strings=5,row_breaks=1))
for item in r['bom']:
    if any(x in item['part_number'] for x in ['CLM','GR-LUG']):
        print(' ', item['qty'], item['part_number'], '-', item['description'])

print()
print('=== 3 rows of 8, no breaks ===')
r2=json.loads(fn(panel_count=24,panel_orientation='portrait',panels_per_row=8,row_breaks=0))
for item in r2['bom']:
    if any(x in item['part_number'] for x in ['CLM','GR-LUG']):
        print(' ', item['qty'], item['part_number'], '-', item['description'])
