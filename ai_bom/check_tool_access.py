"""
Simpler, more reliable handoff:
- bom_calculator: after calculate_solar_bom returns, immediately calls generate_bom_table itself
  so excel_writer has nothing left to do except say TERMINATE.
  This removes the fragile BOM_RESULT_START marker approach entirely.
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# Check what tools bom_calculator has access to
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    tools = p["config"].get("workbench", {}).get("config", {}).get("tools", [])
    print("bom_calculator tools:", [t["config"]["name"] for t in tools])

# Check what tools excel_writer has
for p in data["config"]["participants"]:
    if p["config"]["name"] != "excel_writer":
        continue
    tools = p["config"].get("workbench", {}).get("config", {}).get("tools", [])
    print("excel_writer tools:", [t["config"]["name"] for t in tools])
