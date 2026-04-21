"""Adds the new BOM entries for (N) electrical items using correct dict keys."""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "calculate_solar_bom":
            continue
        src = t["config"]["source_code"]

        if "DISC-FUSED" in src:
            print("BOM entries already present")
            break

        OLD = (
            '    if main_breaker_size > 0:\n'
            '        electrical_bom.append({\n'
            '            "description": f"{main_breaker_size}A Main Panel Breaker",\n'
            '            "part_number": f"MAIN-BR{main_breaker_size}",\n'
            '            "qty": max(main_breaker_quantity, 1),\n'
            '            "unit": "EA",\n'
            '        })\n'
            '\n'
            '    # ── Assemble BOM ──'
        )
        NEW = (
            '    if main_breaker_size > 0:\n'
            '        electrical_bom.append({\n'
            '            "description": f"{main_breaker_size}A Main Panel Breaker",\n'
            '            "part_number": f"MAIN-BR{main_breaker_size}",\n'
            '            "qty": max(main_breaker_quantity, 1),\n'
            '            "unit": "EA",\n'
            '        })\n'
            '\n'
            '    # Fused service-rated AC disconnect (separate from non-fused disconnect)\n'
            '    if fused_disconnect_size > 0:\n'
            '        fuse_desc = ""\n'
            '        if fused_disconnect_fuse_size > 0 and fused_disconnect_fuse_quantity > 0:\n'
            '            fuse_desc = f", ({fused_disconnect_fuse_quantity}) {fused_disconnect_fuse_size}A Fuses"\n'
            '        elif fused_disconnect_fuse_size > 0:\n'
            '            fuse_desc = f", {fused_disconnect_fuse_size}A Fuses"\n'
            '        electrical_bom.append({\n'
            '            "description": f"{fused_disconnect_size}A Service Rated Fused AC Disconnect{fuse_desc}, 240V NEMA 3R",\n'
            '            "part_number": f"DISC-FUSED-{fused_disconnect_size}A",\n'
            '            "qty": 1,\n'
            '            "unit": "EA",\n'
            '        })\n'
            '\n'
            '    # Combiner box (e.g. Q.CELL Q HOME COMBINER 80 G1)\n'
            '    if combiner_box_model:\n'
            '        electrical_bom.append({\n'
            '            "description": f"Combiner Box - {combiner_box_model}, NEMA 3R, UL Listed",\n'
            '            "part_number": "COMBINER",\n'
            '            "qty": 1,\n'
            '            "unit": "EA",\n'
            '        })\n'
            '\n'
            '    # Junction boxes (600V NEMA 3R)\n'
            '    if junction_box_quantity > 0:\n'
            '        electrical_bom.append({\n'
            '            "description": "600V NEMA 3R Junction Box, UL Listed",\n'
            '            "part_number": "JBOX-600V",\n'
            '            "qty": junction_box_quantity,\n'
            '            "unit": "EA",\n'
            '        })\n'
            '\n'
            '    # PV Load Center / MLO sub-panel\n'
            '    if pv_load_center_size > 0:\n'
            '        electrical_bom.append({\n'
            '            "description": f"{pv_load_center_size}A MLO PV Load Center (Sub-Panel), NEMA 3R, UL Listed",\n'
            '            "part_number": f"PV-LC-{pv_load_center_size}A",\n'
            '            "qty": 1,\n'
            '            "unit": "EA",\n'
            '        })\n'
            '\n'
            '    # ── Assemble BOM ──'
        )

        if OLD in src:
            src = src.replace(OLD, NEW)
            print("✅ Added BOM entries for new (N) items")
        else:
            print("⚠️  Anchor not found")

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
print("✅ Saved.")
