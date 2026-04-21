import sqlite3, json

# Get the exact source from DB
db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team = json.loads(row[0])
conn.close()

participants = team['config']['participants']
source_code = None
for p in participants:
    if p['config']['name'] == 'pdf_extractor':
        tools = p['config']['workbench']['config']['tools']
        source_code = tools[0]['config']['source_code']
        break

print("Source code from DB:")
print(source_code[:200])
print()

# Execute it exactly as AutoGen does
namespace = {}
exec(source_code, namespace)
extract_pdf_data = namespace['extract_pdf_data']

# Test it
pdf_path = r"C:\Users\info\OneDrive\Desktop\Engi\documents_v1_drawing-set_1738 Hays St NW - Solar PV Plans.pdf"
print("Calling extract_pdf_data...")
result = extract_pdf_data(pdf_path)
print(f"Result length: {len(result)}")
print()
print("First 2000 chars of result:")
print(result[:2000])
