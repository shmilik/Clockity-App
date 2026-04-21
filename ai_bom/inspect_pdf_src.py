import sqlite3, json
conn = sqlite3.connect(r'C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute('SELECT component FROM team WHERE id=4')
data = json.loads(cur.fetchone()[0])
conn.close()
for p in data['config']['participants']:
    if p['config']['name'] == 'pdf_extractor':
        for t in p['config']['workbench']['config']['tools']:
            if t['config']['name'] == 'extract_pdf_data':
                src = t['config']['source_code']
                lines = src.split('\n')
                for i, line in enumerate(lines[80:160], start=81):
                    print(f"{i:4}: {line}")
