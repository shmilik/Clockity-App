"""
Two changes to calculate_solar_bom:
  1. Ground lugs: qty = num_rows + 4  (1 per row + 4 extra)
  2. End clamps:  qty = 4*num_rows + 4*row_breaks  (extra 4 per mid-row gap)
     New param: row_breaks (int, default 0)

Also updates:
  - Docstring CLAMP RULES to reflect new formulas
  - JSON block in extract_pdf_data to include row_breaks
  - bom_calculator system message to pass row_breaks
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# ─── calculate_solar_bom ─────────────────────────────────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "calculate_solar_bom":
            continue
        src = t["config"]["source_code"]

        # 1a. Add row_breaks to signature
        OLD_SIG = "    combiner_box_model: str = \"\",\n) -> str:"
        NEW_SIG = (
            "    combiner_box_model: str = \"\",\n"
            "    row_breaks: int = 0,\n"
            ") -> str:"
        )
        if "row_breaks" in src:
            print("row_breaks param already present — skipping sig")
        elif OLD_SIG in src:
            src = src.replace(OLD_SIG, NEW_SIG)
            print("✅ Added row_breaks param")
        else:
            print("⚠️  Signature anchor not found")

        # 1b. Update docstring CLAMP RULES
        OLD_CLAMP_DOC = (
            "    CLAMP RULES:\n"
            "      Mid clamps = 2 × (panels_per_row - 1) × num_rows\n"
            "        (2 mid clamps per inter-panel gap: 1 top rail + 1 bottom rail)\n"
            "      End clamps = 4 × num_rows\n"
            "        (2 per row-end × 2 ends per row)\n"
        )
        NEW_CLAMP_DOC = (
            "    CLAMP RULES:\n"
            "      Mid clamps = 2 × (panels_per_row - 1) × num_rows\n"
            "        (2 mid clamps per inter-panel gap: 1 top rail + 1 bottom rail)\n"
            "      End clamps = 4 × num_rows + 4 × row_breaks\n"
            "        (2 per row-end × 2 ends per row, plus 4 extra per mid-row gap/break)\n"
            "      row_breaks = number of gaps/breaks within rows (not between rows)\n"
        )
        if "4 × row_breaks" in src:
            print("Docstring already updated")
        elif OLD_CLAMP_DOC in src:
            src = src.replace(OLD_CLAMP_DOC, NEW_CLAMP_DOC)
            print("✅ Updated docstring CLAMP RULES")
        else:
            print("⚠️  Docstring anchor not found")

        # 1c. Fix end clamp formula
        OLD_CLAMP_CALC = (
            "    total_mid_clamps = 2 * max(panels_per_row - 1, 0) * num_rows\n"
            "    total_end_clamps = 4 * num_rows\n"
        )
        NEW_CLAMP_CALC = (
            "    total_mid_clamps = 2 * max(panels_per_row - 1, 0) * num_rows\n"
            "    total_end_clamps = 4 * num_rows + 4 * max(row_breaks, 0)\n"
        )
        if "4 * max(row_breaks, 0)" in src:
            print("End clamp formula already updated")
        elif OLD_CLAMP_CALC in src:
            src = src.replace(OLD_CLAMP_CALC, NEW_CLAMP_CALC)
            print("✅ Updated end clamp formula")
        else:
            print("⚠️  Clamp calc anchor not found")

        # 1d. Fix ground lug formula
        OLD_LUG = "    total_ground_lugs = num_rows    # 1 per row (not per rail)\n"
        NEW_LUG = "    total_ground_lugs = num_rows + 4  # 1 per row + 4 extra\n"
        if "num_rows + 4" in src:
            print("Ground lug formula already updated")
        elif OLD_LUG in src:
            src = src.replace(OLD_LUG, NEW_LUG)
            print("✅ Updated ground lug formula (num_rows + 4)")
        else:
            print("⚠️  Ground lug anchor not found")

        # 1e. Update BOM table description for ground lugs
        OLD_LUG_DESC = '"Ground Lugs (1 per row)"'
        NEW_LUG_DESC = '"Ground Lugs (1 per row + 4)"'
        if "1 per row + 4" in src:
            print("Ground lug description already updated")
        elif OLD_LUG_DESC in src:
            src = src.replace(OLD_LUG_DESC, NEW_LUG_DESC)
            print("✅ Updated ground lug BOM description")
        else:
            print("⚠️  Ground lug description anchor not found")

        try:
            ast.parse(src)
            print("✅ calculate_solar_bom syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

# ─── extract_pdf_data: add row_breaks to JSON block ──────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        OLD_OVERRIDE = (
            '"override_sticks (int, 0=formula), "\n'
            '            "override_splices (int, 0=formula), "\n'
        )
        NEW_OVERRIDE = (
            '"override_sticks (int, 0=formula), "\n'
            '            "override_splices (int, 0=formula), "\n'
            '            "row_breaks (int, count of mid-row gaps where a continuous panel row is split into separate groups, 0=none), "\n'
        )
        if "row_breaks" in src:
            print("row_breaks already in JSON block")
        elif OLD_OVERRIDE in src:
            src = src.replace(OLD_OVERRIDE, NEW_OVERRIDE)
            print("✅ Added row_breaks to JSON block")
        else:
            print("⚠️  JSON block anchor not found")

        try:
            ast.parse(src)
            print("✅ extract_pdf_data syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

# ─── bom_calculator system message: add row_breaks to CRITICAL list ───────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    msg = p["config"]["system_message"]
    OLD_CRIT_END = "  fused_disconnect_size, fused_disconnect_fuse_size, fused_disconnect_fuse_quantity,\n  junction_box_quantity, pv_load_center_size, combiner_box_model\n"
    NEW_CRIT_END = "  fused_disconnect_size, fused_disconnect_fuse_size, fused_disconnect_fuse_quantity,\n  junction_box_quantity, pv_load_center_size, combiner_box_model,\n  row_breaks\n"
    if "row_breaks" in msg:
        print("row_breaks already in system message")
    elif OLD_CRIT_END in msg:
        p["config"]["system_message"] = msg.replace(OLD_CRIT_END, NEW_CRIT_END)
        print("✅ Added row_breaks to bom_calculator system message")
    else:
        print("⚠️  System message anchor not found")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ All saved.")
