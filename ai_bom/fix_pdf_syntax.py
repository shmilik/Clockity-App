import sqlite3, json

conn = sqlite3.connect(r'C:/Users/info/.autogenstudio/autogen04202.db')
cur = conn.cursor()
cur.execute('SELECT component FROM team WHERE id=4')
data = json.loads(cur.fetchone()[0])

for p in data['config']['participants']:
    if p['config']['name'] == 'pdf_extractor':
        for t in p['config']['workbench']['config']['tools']:
            if t['config']['name'] == 'extract_pdf_data':
                src = t['config']['source_code']

                # Remove the stray extra '(' on the line after '"text": ('
                # Original broken:   "text": (\n    (\n
                # Fixed:             "text": (\n
                old = '                    "text": (\n    (\n'
                new = '                    "text": (\n'
                if old in src:
                    src = src.replace(old, new, 1)
                    print("Fixed: removed extra '('")
                else:
                    print("Marker not found, trying alternate...")
                    # Try stripping line 91 differently
                    lines = src.split('\n')
                    fixed = []
                    skip_next = False
                    for i, line in enumerate(lines):
                        if skip_next:
                            skip_next = False
                            continue
                        fixed.append(line)
                        # If this is the "text": ( line and next is bare (
                        if i + 1 < len(lines) and '"text": (' in line and lines[i+1].strip() == '(':
                            skip_next = True
                            print(f"Stripped bare '(' at line {i+2}")
                    src = '\n'.join(fixed)

                # Validate
                try:
                    compile(src, '<string>', 'exec')
                    print("Source compiles OK")
                except SyntaxError as e:
                    print(f"STILL BROKEN: {e}")
                    conn.close()
                    exit(1)

                t['config']['source_code'] = src

cur.execute('UPDATE team SET component=? WHERE id=4', (json.dumps(data),))
conn.commit()
conn.close()
print("Saved to database.")
