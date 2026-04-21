import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT id, component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team_id, component_json = row
team = json.loads(component_json)

NEW_EXTRACT_SOURCE = r'''
def extract_pdf_data(pdf_path: str) -> str:
    """Extract all text and tables from a solar engineering sheet PDF.
    Accepts an absolute file path.
    Returns the full content as clean markdown for analysis."""
    import os

    if not os.path.exists(pdf_path):
        return f"ERROR: File not found at path: {pdf_path}"

    try:
        import pymupdf4llm
        md_text = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
        if md_text and len(md_text.strip()) > 50:
            return f"PDF extracted successfully via pymupdf4llm:\n\n{md_text}"
    except Exception as e:
        pass  # fall through to pdfplumber

    try:
        import pdfplumber
        pages_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                table_str = ""
                for table in tables:
                    for row in table:
                        if row:
                            table_str += " | ".join(str(c) if c else "" for c in row) + "\n"
                pages_text.append(f"--- Page {i+1} ---\n{text}\n{table_str}")
        combined = "\n".join(pages_text)
        if combined.strip():
            return f"PDF extracted via pdfplumber:\n\n{combined}"
    except Exception as e2:
        return f"ERROR extracting PDF: {e2}"

    return "ERROR: Could not extract any text from the PDF."
'''

# Validate the source code compiles
try:
    compile(NEW_EXTRACT_SOURCE, '<string>', 'exec')
    print("Source code compiles OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    conn.close()
    exit(1)

# Find and update the pdf_extractor tool
participants = team['config']['participants']
updated = False
for p in participants:
    if p['config']['name'] == 'pdf_extractor':
        tools = p['config']['workbench']['config']['tools']
        for tool in tools:
            if tool['config'].get('name') == 'extract_pdf_data':
                print(f"Found tool: {tool['config']['name']}")
                tool['config']['source_code'] = NEW_EXTRACT_SOURCE
                updated = True
                print("Updated source code")

if not updated:
    print("WARNING: Tool not found by name, checking all tools...")
    for p in participants:
        pname = p['config']['name']
        tools = p['config'].get('workbench', {}).get('config', {}).get('tools', [])
        for tool in tools:
            tname = tool['config'].get('name', 'N/A')
            print(f"  Agent={pname}, Tool={tname}")

updated_json = json.dumps(team)
c.execute('UPDATE team SET component = ? WHERE id = ?', (updated_json, team_id))
conn.commit()
print("\nSaved to database!")
conn.close()
