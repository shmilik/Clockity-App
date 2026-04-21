"""
Two formula fixes in calculate_solar_bom:

1. Mid clamp formula: change from 2*(ppr-1)*num_rows to 2*(panel_count - num_rows)
   - Old formula assumes ALL rows have ppr panels (wrong for partial/mixed rows)
   - New formula is always correct: sum of 2*(N-1) over all rows
     = 2*(sum(N) - row_count) = 2*(panel_count - num_rows)
   - Equivalent for uniform rows, correct for mixed-length rows

2. num_rows: add as an explicit JSON param so AI can pass physical row count
   directly from the array diagram instead of deriving from ppr formula

3. Update row_breaks JSON description to be more explicit
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# ── calculate_solar_bom ───────────────────────────────────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "calculate_solar_bom":
            continue
        src = t["config"]["source_code"]

        # A. Add num_rows_override to signature (before row_breaks)
        OLD_SIG = (
            "    row_breaks: int = 0,\n"
            ") -> str:"
        )
        NEW_SIG = (
            "    row_breaks: int = 0,\n"
            "    num_rows_override: int = 0,\n"
            ") -> str:"
        )
        if "num_rows_override" in src:
            print("num_rows_override already in signature")
        elif OLD_SIG in src:
            src = src.replace(OLD_SIG, NEW_SIG)
            print("✅ A: Added num_rows_override param")
        else:
            print("⚠️  A: Signature anchor not found")

        # B. Use num_rows_override when provided
        OLD_NUM_ROWS = (
            "    is_portrait = \"portrait\" in panel_orientation.lower()\n"
            "    num_rows    = math.ceil(panel_count / panels_per_row)\n"
        )
        NEW_NUM_ROWS = (
            "    is_portrait = \"portrait\" in panel_orientation.lower()\n"
            "    num_rows    = num_rows_override if num_rows_override > 0 else math.ceil(panel_count / panels_per_row)\n"
        )
        if "num_rows_override if num_rows_override" in src:
            print("num_rows_override logic already applied")
        elif OLD_NUM_ROWS in src:
            src = src.replace(OLD_NUM_ROWS, NEW_NUM_ROWS)
            print("✅ B: num_rows uses override when provided")
        else:
            print("⚠️  B: num_rows anchor not found")

        # C. Fix mid clamp formula
        OLD_MID = "    total_mid_clamps = 2 * max(panels_per_row - 1, 0) * num_rows\n"
        NEW_MID = (
            "    # 2*(panel_count - num_rows): correct for any row length mix\n"
            "    # = sum of 2*(N-1) for each row = 2*(total_panels - total_rows)\n"
            "    total_mid_clamps = 2 * max(panel_count - num_rows, 0)\n"
        )
        if "2 * max(panel_count - num_rows, 0)" in src:
            print("Mid clamp formula already updated")
        elif OLD_MID in src:
            src = src.replace(OLD_MID, NEW_MID)
            print("✅ C: Mid clamp formula updated to 2*(panel_count - num_rows)")
        else:
            print("⚠️  C: Mid clamp anchor not found")

        # D. Update docstring CLAMP RULES
        OLD_CLAMP_DOC = (
            "      Mid clamps = 2 × (panels_per_row - 1) × num_rows\n"
            "        (2 mid clamps per inter-panel gap: 1 top rail + 1 bottom rail)\n"
        )
        NEW_CLAMP_DOC = (
            "      Mid clamps = 2 × (panel_count - num_rows)\n"
            "        Correct for any row-length mix: sum of 2*(N-1) per row\n"
            "        = 2*(total_panels - total_rows). Equivalent to old formula\n"
            "        for uniform rows; accurate for partial/mixed rows.\n"
        )
        if "Correct for any row-length mix" in src:
            print("Docstring already updated")
        elif OLD_CLAMP_DOC in src:
            src = src.replace(OLD_CLAMP_DOC, NEW_CLAMP_DOC)
            print("✅ D: Updated docstring CLAMP RULES")
        else:
            print("⚠️  D: Docstring anchor not found")

        # E. Update BOM description for mid clamps
        OLD_MID_DESC = '"Mid Clamps [2 per inter-panel gap × 2 rails]"'
        NEW_MID_DESC = '"Mid Clamps [2 × (panels - rows)]"'
        if "2 × (panels - rows)" in src:
            print("Mid clamp BOM description already updated")
        elif OLD_MID_DESC in src:
            src = src.replace(OLD_MID_DESC, NEW_MID_DESC)
            print("✅ E: Updated mid clamp BOM description")
        else:
            print("⚠️  E: Mid clamp BOM description anchor not found")

        try:
            ast.parse(src)
            print("✅ calculate_solar_bom syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

# ── extract_pdf_data: add num_rows and clarify row_breaks in JSON block ───────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        # Add num_rows_override and improve row_breaks description
        OLD_ROW_BREAKS = (
            '"row_breaks (int, count of mid-row gaps where a continuous panel row is split into separate groups, 0=none), "\n'
        )
        NEW_ROW_BREAKS = (
            '"num_rows_override (int, PHYSICAL row count in the array diagram — count distinct horizontal bands of panels, 0=derive from formula), "\n'
            '            "row_breaks (int, count of INTERNAL gaps within rows — where a row is split into 2 separate groups by a gap or obstacle), "\n'
        )
        if "num_rows_override" in src:
            print("num_rows_override already in JSON block")
        elif OLD_ROW_BREAKS in src:
            src = src.replace(OLD_ROW_BREAKS, NEW_ROW_BREAKS)
            print("✅ F: Added num_rows_override and improved row_breaks description")
        else:
            print("⚠️  F: row_breaks JSON block anchor not found")

        try:
            ast.parse(src)
            print("✅ extract_pdf_data syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

# ── bom_calculator system message ─────────────────────────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    msg = p["config"]["system_message"]
    OLD_END = "  junction_box_quantity, pv_load_center_size, combiner_box_model,\n  row_breaks\n"
    NEW_END = "  junction_box_quantity, pv_load_center_size, combiner_box_model,\n  row_breaks, num_rows_override\n"
    if "num_rows_override" in msg:
        print("num_rows_override already in system message")
    elif OLD_END in msg:
        p["config"]["system_message"] = msg.replace(OLD_END, NEW_END)
        print("✅ G: Added num_rows_override to system message CRITICAL list")
    else:
        print("⚠️  G: System message anchor not found")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ All saved.")
