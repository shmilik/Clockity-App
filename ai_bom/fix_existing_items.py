"""
Targeted fixes for (E)/(N) issues:
1. main_breaker_size in JSON block → add explicit "(N) items only, 0 if marked (E)"
2. disconnect_size in JSON block → clarify "NON-FUSED only"
3. Remove confusing old fuse_size / fuse_quantity fields from JSON block
4. Vision prompt INTERCONNECTION → add explicit (N)/(E) reminder for pv_breaker_size
   and remove any implicit main_breaker reference that could pull (E) items
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        # ── Fix 1: main_breaker_size — add (N) only guard ────────────────────
        OLD_MAIN = (
            '"main_breaker_size (int amps of the main panel service breaker e.g. 200, 0=not found), "\n'
            '            "main_breaker_quantity (int, usually 1), "\n'
        )
        NEW_MAIN = (
            '"main_breaker_size (int amps — ONLY if marked (N) NEW, output 0 if it is marked (E) EXISTING), "\n'
            '            "main_breaker_quantity (int, usually 1, 0 if main_breaker_size is 0), "\n'
        )
        if "(N) NEW, output 0 if it is marked (E)" in src:
            print("Fix 1 already applied")
        elif OLD_MAIN in src:
            src = src.replace(OLD_MAIN, NEW_MAIN)
            print("✅ Fix 1: main_breaker_size (N) guard added")
        else:
            print("⚠️  Fix 1 anchor not found")

        # ── Fix 2: disconnect_size — clarify NON-FUSED only ──────────────────
        OLD_DISC = '"disconnect_size (int amps of the AC disconnect unit, 0=not found), "'
        NEW_DISC = '"disconnect_size (int amps of the NON-FUSED AC disconnect only — 0 if not found or marked (E)), "'
        if "NON-FUSED AC disconnect only" in src:
            print("Fix 2 already applied")
        elif OLD_DISC in src:
            src = src.replace(OLD_DISC, NEW_DISC)
            print("✅ Fix 2: disconnect_size clarified as NON-FUSED")
        else:
            print("⚠️  Fix 2 anchor not found")

        # ── Fix 3: remove confusing legacy fuse_size / fuse_quantity fields ──
        OLD_FUSE = (
            '"fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
            '            "fuse_quantity (int number of fuses, 0=derive from strings), "\n'
        )
        NEW_FUSE = (
            '"fuse_size (int — DEPRECATED, use fused_disconnect_fuse_size instead, output 0), "\n'
            '            "fuse_quantity (int — DEPRECATED, use fused_disconnect_fuse_quantity instead, output 0), "\n'
        )
        if "DEPRECATED, use fused_disconnect_fuse_size" in src:
            print("Fix 3 already applied")
        elif OLD_FUSE in src:
            src = src.replace(OLD_FUSE, NEW_FUSE)
            print("✅ Fix 3: deprecated fuse_size / fuse_quantity")
        else:
            print("⚠️  Fix 3 anchor not found")

        # ── Fix 4: Vision prompt — reinforce (N)/(E) in INTERCONNECTION ──────
        OLD_INTERCON = (
            '"INTERCONNECTION:\\n"\n'
            '                        "- interconnection_method = <load side tap | line side tap | supply side | meter socket | utility backfeed>\\n"\n'
            '                        "- pv_breaker_size = <amperage of the PV breaker at point of interconnect, e.g. 80>  (0 if none)\\n"\n'
            '                        "- num_strings = <number of DC string circuits shown>\\n\\n"\n'
            '                        "FUSING — for has_fused_disconnect field only:\\n"\n'
            '                        "- has_fused_disconnect = True if a fused disconnect exists, False otherwise\\n\\n"\n'
            '                        "Output only the labeled fields above. If a field is not shown, use 0 or empty string."'
        )
        NEW_INTERCON = (
            '"INTERCONNECTION:\\n"\n'
            '                        "- interconnection_method = <load side tap | line side tap | supply side | meter socket | utility backfeed>\\n"\n'
            '                        "- pv_breaker_size = <amperage of the (N) NEW PV breaker at point of interconnect>  (0 if none or if marked (E))\\n"\n'
            '                        "- num_strings = <number of DC string circuits shown>\\n\\n"\n'
            '                        "EXISTING items — SKIP COMPLETELY (output 0 or empty):\\n"\n'
            '                        "- Any item labeled (E) must NOT be listed — output 0 for its size field.\\n"\n'
            '                        "- Common (E) items: utility meter, main service panel, existing main breaker.\\n\\n"\n'
            '                        "FUSING — for has_fused_disconnect field only:\\n"\n'
            '                        "- has_fused_disconnect = True if a (N) NEW fused disconnect exists, False otherwise\\n\\n"\n'
            '                        "Output only the labeled fields above. If a field is not shown or is marked (E), use 0 or empty string."'
        )
        if "(E) must NOT be listed" in src:
            print("Fix 4 already applied")
        elif OLD_INTERCON in src:
            src = src.replace(OLD_INTERCON, NEW_INTERCON)
            print("✅ Fix 4: Vision prompt (E) guard added")
        else:
            print("⚠️  Fix 4 anchor not found")

        try:
            ast.parse(src)
            print("✅ Syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ Saved.")
