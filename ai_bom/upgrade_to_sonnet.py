"""
Upgrades all agents in Solar BOM team (id=4) from claude-haiku to claude-sonnet-4-5.
Also replaces hardcoded model strings inside extract_pdf_data tool source.
"""
import sqlite3, json, re

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
OLD_MODEL = "claude-haiku-4-5-20251001"
NEW_MODEL = "claude-sonnet-4-5-20251001"

conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    name = p["config"]["name"]

    # 1. Agent model_client
    mc = p["config"]["model_client"]["config"]
    if mc.get("model") == OLD_MODEL:
        mc["model"] = NEW_MODEL
        print(f"  Agent model: {name} -> {NEW_MODEL}")

    # 2. Hardcoded model strings inside tool source code
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        tname = t["config"]["name"]
        src   = t["config"]["source_code"]
        new_src = src.replace(f'model="{OLD_MODEL}"', f'model="{NEW_MODEL}"')
        if new_src != src:
            t["config"]["source_code"] = new_src
            count = src.count(f'model="{OLD_MODEL}"')
            print(f"  Tool source: {tname} — replaced {count} occurrence(s)")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done — all agents now use", NEW_MODEL)
