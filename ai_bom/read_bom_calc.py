import sqlite3, json
conn = sqlite3.connect('C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute('SELECT component FROM team WHERE id=4')
data = json.loads(cur.fetchone()[0])
conn.close()
for p in data['config']['participants']:
    if p['config']['name'] == 'bom_calculator':
        print('=== SYSTEM MESSAGE ===')
        print(p['config'].get('system_message',''))
        print()
        for t in p['config']['workbench']['config']['tools']:
            name = t['config']['name']
            print(f'=== TOOL: {name} ===')
            print(t['config'].get('source_code',''))
            print()
