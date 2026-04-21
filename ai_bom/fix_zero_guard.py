"""Inserts the panels_per_row=0 guard before the first use of panels_per_row."""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "calculate_solar_bom":
            continue
        src = t["config"]["source_code"]

        if "Guard against zero" in src:
            print("Guard already present")
            break

        OLD = '    is_portrait = "portrait" in panel_orientation.lower()\n    num_rows    = math.ceil(panel_count / panels_per_row)\n'
        NEW = (
            '    # Guard against zero values that would cause division errors\n'
            '    if panels_per_row <= 0:\n'
            '        panels_per_row = max(1, panel_count)\n'
            '    if panel_count <= 0:\n'
            '        panel_count = 1\n'
            '    is_portrait = "portrait" in panel_orientation.lower()\n'
            '    num_rows    = math.ceil(panel_count / panels_per_row)\n'
        )
        if OLD in src:
            src = src.replace(OLD, NEW)
            print("✅ Guard inserted")
        else:
            print("⚠️  Anchor not found")

        try:
            ast.parse(src)
            print("✅ Syntax OK")
        except SyntaxError as e:
            print(f"❌ {e}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("✅ Saved.")
