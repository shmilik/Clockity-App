"""
Repairs the syntax error introduced by fix_bom_params.py.
The JSON_PARAMS_INSTRUCTION was injected with raw newlines into a Python string
literal, causing an unterminated string literal at line 293.
This script replaces the broken section with properly escaped Python code.
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"

# ── The broken text as it exists in source_code right now ─────────────────────
# (actual newlines were injected into the string literal)
BROKEN_START = '"Keep answers concise. Use the exact labels above so the BOM Calculator can parse them.'
BROKEN_END   = 'panel_count MUST be the actual number of panels on the roof \u2014 count carefully from the layout.\\n\\n"'

# ── The correct Python source code lines to replace the broken section ─────────
# Uses \n escape sequences (not actual newlines) so the string literal is valid.
FIXED = (
    '"Keep answers concise. Use the exact labels above so the BOM Calculator can parse them.\\n\\n"\n'
    '            "IMPORTANT: After your text analysis, output a JSON object in a ```json code block\\n"\n'
    '            "with exactly these keys (use 0 for unknown ints, false for unknown bools):\\n"\n'
    '            "panel_count (int - actual total panels), "\n'
    '            "panel_orientation (portrait or landscape), "\n'
    '            "panels_per_row (int), "\n'
    '            "panel_width_in (float, default 40.9), "\n'
    '            "panel_height_in (float, default 67.9), "\n'
    '            "inverter_count (int, 0=1 per panel), "\n'
    '            "inverter_system (enphase_iq|qcells_integrated|hoymiles|solaredge|string|string_central), "\n'
    '            "rail_system (IronRidge XR10|IronRidge XR100|IronRidge QM ClickFit|Unirac SolarMount), "\n'
    '            "rail_length_ft (float, default 14.0), "\n'
    '            "roof_attachment (comp_shingle|tile|metal_standing_seam|flat), "\n'
    '            "mounting_foot_count (int, 0=use formula), "\n'
    '            "num_strings (int, 0=unknown), "\n'
    '            "override_sticks (int, 0=formula), "\n'
    '            "override_splices (int, 0=formula), "\n'
    '            "has_fused_disconnect (boolean), "\n'
    '            "pv_breaker_size (int amps, 0=none).\\n"\n'
    '            "panel_count MUST match the actual installed panel count.\\n\\n"'
)

conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

fixed_any = False

for p in data["config"]["participants"]:
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue

        src = t["config"]["source_code"]

        # Find the broken block
        start_idx = src.find(BROKEN_START)
        if start_idx == -1:
            print("ERROR: Could not find BROKEN_START in source — already fixed?")
            break

        end_idx = src.find(BROKEN_END)
        if end_idx == -1:
            print("ERROR: Could not find BROKEN_END in source.")
            break

        end_idx += len(BROKEN_END)

        # Build the repaired source
        new_src = src[:start_idx] + FIXED + src[end_idx:]

        # Verify it compiles before saving
        try:
            ast.parse(new_src)
            print("✅ Syntax check passed")
        except SyntaxError as e:
            print(f"❌ Syntax error after repair at line {e.lineno}: {e.msg}")
            # Print context around the error
            lines = new_src.splitlines()
            for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+3)):
                print(f"  {i+1}: {repr(lines[i])}")
            conn.close()
            raise SystemExit(1)

        t["config"]["source_code"] = new_src
        fixed_any = True
        print(f"✅ Repaired extract_pdf_data ({len(src)} -> {len(new_src)} chars)")

if fixed_any:
    cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
    conn.commit()
    print("✅ DB updated — ready to test.")
else:
    print("No changes made.")

conn.close()
