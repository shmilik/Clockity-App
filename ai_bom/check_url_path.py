import sqlite3, json

DB = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])
conn.close()

# excel_writer is participant index 2, tool 0 = generate_bom_table
for p in data['config']['participants']:
    if p['config']['name'] == 'excel_writer':
        tools = p['config']['workbench']['config']['tools']
        src = tools[0]['config']['source_code']
        # find apps_script_url references
        for i, line in enumerate(src.split('\n')):
            if 'apps_script' in line.lower() or 'script_url' in line.lower():
                print(f"Line {i}: {line}")
