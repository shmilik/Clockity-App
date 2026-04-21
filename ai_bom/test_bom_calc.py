import sqlite3, json, sys
sys.path.insert(0, r'C:\Users\info\OneDrive\Desktop\JobTracker')

conn = sqlite3.connect(r'C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute('SELECT component FROM team WHERE id=4')
data = json.loads(cur.fetchone()[0])
conn.close()

src = ''
for p in data['config']['participants']:
    if p['config']['name'] == 'bom_calculator':
        for t in p['config']['workbench']['config']['tools']:
            if t['config']['name'] == 'calculate_solar_bom':
                src = t['config']['source_code']

ns = {}
exec(src, ns)
calc = ns['calculate_solar_bom']

# 1738 Hays St: 24 panels, landscape, 4/row, 6 rows, QM ClickFit, comp shingle,
#               Q.CELLS Q.MI microinverter, 58 mounting feet from vision blue dots
result = json.loads(calc(
    panel_count=24,
    panel_orientation="landscape",
    panels_per_row=4,
    panel_height_in=67.9,
    inverter_count=24,
    inverter_system="qcells_integrated",
    rail_system="IronRidge QM ClickFit",
    rail_length_ft=14,
    roof_attachment="comp_shingle",
    mounting_foot_count=58,
))

print("SUMMARY:", result['summary'])
print()
print(f"{'QTY':>5}  {'PART':20}  {'DESCRIPTION'}")
print("-" * 80)
for item in result['bom']:
    print(f"{item['qty']:>5}  {item['part_number']:20}  {item['description']}")

# Spot-check clamp math
print()
print("CLAMP CHECK (6 rows × 4 panels):")
print(f"  Mid clamps should be 2×(4-1)×6 = 36")
print(f"  End clamps should be 4×6        = 24")
mids = next(i for i in result['bom'] if 'Mid' in i['description'])
ends = next(i for i in result['bom'] if 'End' in i['description'])
print(f"  Got mids={mids['qty']}  ends={ends['qty']}")
print(f"  {'✓ PASS' if mids['qty']==36 and ends['qty']==24 else '✗ FAIL'}")
