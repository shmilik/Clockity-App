"""
Adds the missing new fields to the JSON block in extract_pdf_data's main parsing prompt.
Also adds a ZeroDivisionError guard to calculate_solar_bom for panels_per_row=0.
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# ── 1. Add new fields to extract_pdf_data JSON block ─────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        if "fused_disconnect_size" in src and "combiner_box_model" in src and "json" in src[src.find("main_breaker_quantity"):src.find("main_breaker_quantity")+500]:
            # Check if it's in the JSON block specifically
            idx = src.find('"main_breaker_quantity (int, usually 1)')
            after = src[idx:idx+600]
            if "fused_disconnect_size" in after:
                print("JSON block already has new fields — skipping")
                break

        OLD_JSON_END = (
            '"main_breaker_size (int amps of the main panel service breaker e.g. 200, 0=not found), "\n'
            '            "main_breaker_quantity (int, usually 1).\\n"\n'
            '            "panel_count MUST match the actual installed panel count.'
        )
        NEW_JSON_END = (
            '"main_breaker_size (int amps of the main panel service breaker e.g. 200, 0=not found), "\n'
            '            "main_breaker_quantity (int, usually 1), "\n'
            '            "fused_disconnect_size (int amps of the fused service-rated AC disconnect if labeled (N), 0=not found), "\n'
            '            "fused_disconnect_fuse_size (int amps per fuse e.g. 125, 0=not found), "\n'
            '            "fused_disconnect_fuse_quantity (int number of fuses e.g. 2, 0=not found), "\n'
            '            "junction_box_quantity (int count of (N) junction boxes, 0=none), "\n'
            '            "pv_load_center_size (int amps of (N) MLO PV load center, 0=not found), "\n'
            '            "combiner_box_model (string model name of (N) combiner box, empty string if none).\\n"\n'
            '            "CRITICAL: Only include (N) NEW items. Skip all (E) EXISTING items.\\n"\n'
            '            "panel_count MUST match the actual installed panel count.'
        )
        if OLD_JSON_END in src:
            src = src.replace(OLD_JSON_END, NEW_JSON_END)
            print("✅ Added new fields to JSON block in extract_pdf_data")
        else:
            print("⚠️  Could not find JSON block anchor — checking alternate")
            # Try alternate: maybe the period is different
            alt = (
                '"main_breaker_quantity (int, usually 1).\\n"\n'
                '            "panel_count MUST match the actual installed panel count.'
            )
            if alt in src:
                src = src.replace(alt,
                    '"main_breaker_quantity (int, usually 1), "\n'
                    '            "fused_disconnect_size (int amps of the fused service-rated AC disconnect if labeled (N), 0=not found), "\n'
                    '            "fused_disconnect_fuse_size (int amps per fuse e.g. 125, 0=not found), "\n'
                    '            "fused_disconnect_fuse_quantity (int number of fuses e.g. 2, 0=not found), "\n'
                    '            "junction_box_quantity (int count of (N) junction boxes, 0=none), "\n'
                    '            "pv_load_center_size (int amps of (N) MLO PV load center, 0=not found), "\n'
                    '            "combiner_box_model (string model name of (N) combiner box, empty string if none).\\n"\n'
                    '            "CRITICAL: Only include (N) NEW items. Skip all (E) EXISTING items.\\n"\n'
                    '            "panel_count MUST match the actual installed panel count.'
                )
                print("✅ Added new fields to JSON block (alt match)")
            else:
                print("⚠️  Could not add new fields — no anchor found")

        try:
            ast.parse(src)
            print("✅ extract_pdf_data syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

# ── 2. Guard panels_per_row=0 in calculate_solar_bom ─────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "calculate_solar_bom":
            continue
        src = t["config"]["source_code"]

        OLD_GUARD = '    import math\n'
        NEW_GUARD = (
            '    import math\n'
            '    # Guard against zero/negative values that would cause division errors\n'
            '    if panels_per_row <= 0:\n'
            '        panels_per_row = max(1, panel_count)  # treat as single row\n'
            '    if panel_count <= 0:\n'
            '        panel_count = 1  # prevent empty BOM; caller should provide real count\n'
        )
        if "Guard against zero/negative" in src:
            print("Guard already present — skipping")
        elif OLD_GUARD in src:
            src = src.replace(OLD_GUARD, NEW_GUARD, 1)
            print("✅ Added panels_per_row guard")
        else:
            print("⚠️  Could not find 'import math' anchor for guard")

        try:
            ast.parse(src)
            print("✅ calculate_solar_bom syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ All saved.")
