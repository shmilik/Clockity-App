"""Fix disconnect_size description in vision prompt to clarify it's the enclosure amps."""
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

        # Fix 1: vision prompt — disconnect_size label
        OLD = (
            '"- disconnect_size = <integer amps, e.g. 200>  (0 if not found)\\n"\n'
            '                        "- disconnect_brand = <brand name or empty>\\n\\n"\n'
        )
        NEW = (
            '"- disconnect_size = <ENCLOSURE amp rating e.g. 200 — NOT the fuse size>  (0 if not found)\\n"\n'
            '                        "- disconnect_brand = <brand name or empty>\\n\\n"\n'
        )
        if "ENCLOSURE amp rating" in src:
            print("Fix 1 already applied")
        elif OLD in src:
            src = src.replace(OLD, NEW)
            print("✅ Fix 1: disconnect_size clarified as enclosure amps in vision prompt")
        else:
            print("⚠️  Fix 1 anchor not found")
            i = src.find("disconnect_size = <integer")
            print(repr(src[max(0,i-20):i+120]))

        # Fix 2: JSON block — disconnect_size description
        OLD2 = '"disconnect_size (int amps of the NON-FUSED AC disconnect only — 0 if not found or marked (E)), "'
        NEW2 = '"disconnect_size (int amps of the NON-FUSED disconnect ENCLOSURE e.g. 200 — this is NOT the fuse size; 0 if not found or marked (E)), "'
        if "this is NOT the fuse size" in src:
            print("Fix 2 already applied")
        elif OLD2 in src:
            src = src.replace(OLD2, NEW2)
            print("✅ Fix 2: disconnect_size JSON block clarified")
        else:
            print("⚠️  Fix 2 anchor not found")

        try:
            ast.parse(src)
            print("✅ Syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(d),))
conn.commit()
conn.close()
print("✅ Saved.")
