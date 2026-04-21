import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        # The exact old text in the JSON params block
        OLD = (
            '"fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
            '            "fuse_quantity (int number of fuses, 0=derive from strings).\\n"\n'
            '            "panel_count MUST match the actual installed panel count.\\n\\n"'
        )
        NEW = (
            '"fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
            '            "fuse_quantity (int number of fuses, 0=derive from strings), "\n'
            '            "pv_breaker_quantity (int number of PV breakers, usually 1 or equal to num_strings), "\n'
            '            "main_breaker_size (int amps of the main panel service breaker e.g. 200, 0=not found), "\n'
            '            "main_breaker_quantity (int, usually 1).\\n"\n'
            '            "panel_count MUST match the actual installed panel count.\\n\\n"'
        )

        if OLD in src:
            src = src.replace(OLD, NEW)
            t["config"]["source_code"] = src
            ast.parse(src)
            print("Patched + syntax OK")
        else:
            # Show what's actually there around fuse_quantity
            idx = src.find('"fuse_quantity (int number')
            print("Old anchor not found. Context around fuse_quantity:")
            print(repr(src[max(0,idx-5):idx+200]))

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
