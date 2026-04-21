"""Diagnose why Google Sheet is not being created."""
import sqlite3, json, os

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
c = sqlite3.connect(DB).cursor()
c.execute("SELECT component FROM team WHERE id=4")
d = json.loads(c.fetchone()[0])

print("=== AGENT SYSTEM MESSAGES ===")
for p in d["config"]["participants"]:
    name = p["config"]["name"]
    print(f"\n--- {name} ---")
    print(p["config"]["system_message"][:500])

print("\n\n=== TESTING generate_bom_table DIRECTLY ===")
# Load the tool source
for p in d["config"]["participants"]:
    if p["config"]["name"] != "excel_writer":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] == "generate_bom_table":
            src = t["config"]["source_code"]

# Test with minimal BOM
g = {"json": json}
exec(src, g)
fn = g["generate_bom_table"]

test_bom = json.dumps({
    "summary": "Test run",
    "bom": [
        {"part_number": "SEE-ENGINEERING", "description": "Solar Panels", "qty": 48, "unit": "EA"},
        {"part_number": "DISC-200A", "description": "200A AC Disconnect", "qty": 1, "unit": "EA"},
    ]
})

print("\nCalling generate_bom_table...")
result = fn(test_bom, job_name="Diagnostic Test")
print(result[:1000])
