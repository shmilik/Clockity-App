import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
d = json.loads(cur.fetchone()[0])

for p in d["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        OLD = '"panel_count MUST match the actual installed panel count.\\n\\n"'
        NEW = (
            '"panel_count MUST match the actual installed panel count.\\n"'
            '            "IMPORTANT: If a PAGE 1 ARRAY LAYOUT (vision count) section is present '
            'in the text above, use those values for panel_count, num_rows_override, '
            'row_breaks, and panels_per_row — they are more accurate than text-derived values.\\n\\n"'
        )

        if "PAGE 1 ARRAY LAYOUT (vision count) section" in src:
            print("Already updated")
        elif OLD in src:
            src = src.replace(OLD, NEW)
            try:
                ast.parse(src)
                print("✅ Updated; syntax OK")
            except SyntaxError as e:
                print(f"❌ Syntax error line {e.lineno}: {e.msg}")
                conn.close()
                raise SystemExit(1)
            t["config"]["source_code"] = src
        else:
            print("⚠️  Anchor not found")
            i = src.find("panel_count MUST match")
            print(repr(src[i:i+120]))

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(d),))
conn.commit()
conn.close()
print("✅ Saved.")
