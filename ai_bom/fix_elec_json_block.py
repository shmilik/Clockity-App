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
        OLD = '"pv_breaker_size (int amps, 0=none).\\n"'
        NEW = (
            '"pv_breaker_size (int amps, 0=none), "\n'
            '            "disconnect_size (int amps of the AC disconnect unit, 0=not found), "\n'
            '            "disconnect_quantity (int, usually 1), "\n'
            '            "disconnect_brand (string brand name or empty string), "\n'
            '            "fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
            '            "fuse_quantity (int number of fuses, 0=derive from strings).\\n"'
        )
        if OLD in src:
            src = src.replace(OLD, NEW)
            t["config"]["source_code"] = src
            ast.parse(src)
            print("Patched + syntax OK")
        else:
            idx = src.find("pv_breaker_size (int amps")
            print("Anchor not found. Context:", repr(src[max(0,idx-5):idx+60]))

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
