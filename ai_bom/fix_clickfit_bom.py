import sqlite3, json

DB = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data['config']['participants']:
    if p['config']['name'] == 'bom_calculator':
        tools = p['config']['workbench']['config']['tools']
        for t in tools:
            src = t['config']['source_code']
            if 'calculate_solar_bom' not in src[:100]:
                continue

            # ── 1. Fix ground lug formula ──────────────────────────────────────
            src = src.replace(
                'total_ground_lugs = num_rows + 4  # 1 per row + 4 extra',
                'total_ground_lugs = num_rows + max(row_breaks, 0)  # 1 per continuous row, +1 per break'
            )
            assert 'total_ground_lugs = num_rows + max(row_breaks, 0)' in src, "Ground lug fix failed"
            print("✓ Ground lug formula fixed")

            # ── 2. Replace qmclickfit PARTS entry with EcoFasten real part numbers ──
            old_part = ('        "qmclickfit":  {"rail": "QM-CF-SD-168M",  "splice": "QM-CF-SPLICE", '
                        '"mid": "QM-MIDCLAMP","end": "QM-ENDCLAMP","wire_clip": "","ground_lug": "QM-GR-LUG",  '
                        '"t_bolt": "QM-CLICKER-BOLT","screw": "QM-SS-SCREW"},')
            new_part = ('        "clickfit":    {"rail": "2012035",         "splice": "2012045",      '
                        '"mid": "2099045",   "end": "2099046",   "wire_clip": "","ground_lug": "SGB4",        '
                        '"smartfoot": "2012028","t_bolt": "",              "screw": "3016018",    "end_cap": "2012029"},')
            src = src.replace(old_part, new_part)
            assert '"clickfit"' in src, "ClickFit PARTS entry not inserted"
            print("✓ Replaced qmclickfit with EcoFasten ClickFit part numbers")

            # ── 3. Update pick_parts() to detect ecofasten + clickfit ─────────
            src = src.replace(
                'if "clickfit" in rs or "qmcf" in rs:           return PARTS["qmclickfit"]',
                'if "clickfit" in rs or "ecofasten" in rs:      return PARTS["clickfit"]'
            )
            assert 'return PARTS["clickfit"]' in src, "pick_parts update failed"
            print("✓ pick_parts updated for EcoFasten/ClickFit")

            # ── 4. Add is_clickfit flag + SmartFoot override after pick_parts call ──
            old_pn_block = (
                '    pn       = pick_parts(rail_system)\n'
                '    foot_pn  = FOOT_PARTS.get(roof_attachment, "FW-LFAB-200B")\n'
            )
            new_pn_block = (
                '    pn       = pick_parts(rail_system)\n'
                '    is_clickfit = "clickfit" in rail_system.lower() or "ecofasten" in rail_system.lower()\n'
                '    foot_pn  = FOOT_PARTS.get(roof_attachment, "FW-LFAB-200B")\n'
                '    if is_clickfit:\n'
                '        foot_pn = pn.get("smartfoot", "2012028")  # EcoFasten SmartFoot overrides roof-type foot\n'
            )
            src = src.replace(old_pn_block, new_pn_block)
            assert 'is_clickfit' in src, "is_clickfit flag not inserted"
            print("✓ is_clickfit flag + SmartFoot override added")

            # ── 5. Update BOM assembly: foot description, t_bolt, end caps ─────
            old_foot_block = (
                '        {"description": "Mounting Feet ({roof_attachment}) [{foot_source}]",\n'
                '         "part_number": foot_pn,             "qty": total_feet,        "unit": "EA"},\n'
                '        {"description": "T-Bolts / Clicker Bolts (1 per foot)",\n'
                '         "part_number": pn["t_bolt"],        "qty": total_feet,        "unit": "EA"},\n'
                '        {"description": "Stainless Hex Screws (3 per foot)",\n'
                '         "part_number": pn["screw"],         "qty": total_feet * 3,    "unit": "EA"},\n'
            )
            new_foot_block = (
                '        {"description": ("EcoFasten SmartFoot w/ Clicker (1 per attachment)" if is_clickfit\n'
                '                         else f"Mounting Feet ({roof_attachment}) [{foot_source}]"),\n'
                '         "part_number": foot_pn, "qty": total_feet, "unit": "EA"},\n'
                '        {"description": "T-Bolts / Clicker Bolts (1 per foot)",\n'
                '         "part_number": pn["t_bolt"], "qty": 0 if is_clickfit else total_feet, "unit": "EA"},\n'
                '        {"description": "Stainless Hex Screws (3 per foot)",\n'
                '         "part_number": pn["screw"], "qty": total_feet * 3, "unit": "EA"},\n'
                '        {"description": "End Caps (1 per end clamp position, ClickFit only)",\n'
                '         "part_number": pn.get("end_cap", ""), "qty": total_end_clamps if is_clickfit else 0, "unit": "EA"},\n'
            )
            src = src.replace(old_foot_block, new_foot_block)
            assert 'EcoFasten SmartFoot' in src, "Foot/endcap BOM block update failed"
            print("✓ Foot, t-bolt, end cap BOM lines updated")

            # ── 6. Fix ground lug BOM description ──────────────────────────────
            src = src.replace(
                '"Ground Lugs (1 per row + 4)",   ',
                '"Ground Lugs (1 per continuous row + 1 per break)",   '
            )
            print("✓ Ground lug BOM description updated")

            # ── 7. Fix summary string ───────────────────────────────────────────
            src = src.replace(
                'f"Ground lugs: {total_ground_lugs} (1/row). "',
                'f"Ground lugs: {total_ground_lugs} (1/row+break). "'
            )
            print("✓ Summary string updated")

            t['config']['source_code'] = src
            print()

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done — calculate_solar_bom updated with ClickFit/EcoFasten parts and corrected formulas.")
