"""
Patches the generate_bom_table tool in team id=4 (Solar BOM Team)
to use Google Sheets export instead of Excel.
Reads tool source from bom_google_sheet_tool.py to avoid escape issues.
"""
import sqlite3, json, os

DB       = r"C:\Users\info\.autogenstudio\autogen04202.db"
SRC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bom_google_sheet_tool.py")

with open(SRC_FILE, encoding="utf-8") as f:
    NEW_SOURCE = f.read()

NEW_DESCRIPTION = (
    "Format the solar BOM as a markdown table visible in the agent chat, "
    "then create a Google Sheet (BOM Detail + Order Sheet tabs) shared to "
    "apais@unicitysolar.com. Returns the table and the Google Sheet URL."
)

conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

patched = False
for p in data["config"]["participants"]:
    if p["config"]["name"] == "excel_writer":
        tools = p["config"]["workbench"]["config"]["tools"]
        for t in tools:
            src = t["config"].get("source_code", "")
            if "generate_bom" in src:
                t["config"]["source_code"] = NEW_SOURCE
                t["description"] = NEW_DESCRIPTION
                patched = True
                print("Updated generate_bom_table -> Google Sheets export")

if patched:
    cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
    conn.commit()
    print("Saved to DB.")
else:
    print("ERROR: generate_bom_table tool not found in excel_writer agent.")

conn.close()
