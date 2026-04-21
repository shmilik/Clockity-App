"""
Adds main breaker and PV breaker quantity to calculate_solar_bom + extract_pdf_data JSON block.

New parameters:
  pv_breaker_quantity  : int - number of PV breakers (default 1; one per string for some configs)
  main_breaker_size    : int - main panel breaker amperage (e.g. 200)
  main_breaker_quantity: int - number of main breakers listed (usually 1)
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    name = p["config"]["name"]
    tools = p["config"].get("workbench", {}).get("config", {}).get("tools", [])

    # ── 1. calculate_solar_bom ────────────────────────────────────────────────
    if name == "bom_calculator":
        for t in tools:
            if t["config"]["name"] != "calculate_solar_bom":
                continue
            src = t["config"]["source_code"]

            # a) Add new params to signature
            OLD_SIG = (
                "    fuse_size: int = 0,\n"
                "    fuse_quantity: int = 0,\n"
                ") -> str:"
            )
            NEW_SIG = (
                "    fuse_size: int = 0,\n"
                "    fuse_quantity: int = 0,\n"
                "    pv_breaker_quantity: int = 1,\n"
                "    main_breaker_size: int = 0,\n"
                "    main_breaker_quantity: int = 1,\n"
                ") -> str:"
            )
            if "main_breaker_size" in src:
                print("main_breaker_size already in signature — skipping sig patch")
            elif OLD_SIG in src:
                src = src.replace(OLD_SIG, NEW_SIG)
                print("✅ Added pv_breaker_quantity + main_breaker params to signature")
            else:
                print("⚠️  Could not find signature anchor!")

            # b) Fix PV breaker to use pv_breaker_quantity, and add main breaker block
            OLD_PV = (
                '            electrical_bom = [\n'
                '                {"description": f"{pv_breaker_size}A/2P PV Interconnect Breaker",\n'
                '                 "part_number": f"BR{pv_breaker_size}",  "qty": 1,  "unit": "EA"},\n'
                '            ]\n'
            )
            NEW_PV = (
                '            electrical_bom = [\n'
                '                {"description": f"{pv_breaker_size}A/2P PV Interconnect Breaker",\n'
                '                 "part_number": f"BR{pv_breaker_size}",\n'
                '                 "qty": max(pv_breaker_quantity, 1), "unit": "EA"},\n'
                '            ]\n'
            )
            if "max(pv_breaker_quantity" in src:
                print("PV breaker quantity already patched — skipping")
            elif OLD_PV in src:
                src = src.replace(OLD_PV, NEW_PV)
                print("✅ PV breaker now uses pv_breaker_quantity")
            else:
                print("⚠️  Could not find PV breaker block!")

            # c) Add main breaker line item after the fuse block
            OLD_FUSE_END = (
                '    # ── Fuses (inside fused disconnect or separate combiner) ───────────────\n'
                '    if fuse_size > 0:\n'
                '        actual_fuse_qty = fuse_quantity if fuse_quantity > 0 else strings * 2\n'
                '        electrical_bom.append({\n'
                '            "description": f"{fuse_size}A Cartridge Fuse (for fused disconnect)",\n'
                '            "part_number": f"FUSE-{fuse_size}A",\n'
                '            "qty": actual_fuse_qty,\n'
                '            "unit": "EA",\n'
                '        })\n'
            )
            NEW_FUSE_END = (
                '    # ── Fuses (inside fused disconnect or separate combiner) ───────────────\n'
                '    if fuse_size > 0:\n'
                '        actual_fuse_qty = fuse_quantity if fuse_quantity > 0 else strings * 2\n'
                '        electrical_bom.append({\n'
                '            "description": f"{fuse_size}A Cartridge Fuse (for fused disconnect)",\n'
                '            "part_number": f"FUSE-{fuse_size}A",\n'
                '            "qty": actual_fuse_qty,\n'
                '            "unit": "EA",\n'
                '        })\n'
                '\n'
                '    # ── Main service panel breaker ────────────────────────────────────────\n'
                '    if main_breaker_size > 0:\n'
                '        electrical_bom.append({\n'
                '            "description": f"{main_breaker_size}A Main Panel Breaker",\n'
                '            "part_number": f"MAIN-BR{main_breaker_size}",\n'
                '            "qty": max(main_breaker_quantity, 1),\n'
                '            "unit": "EA",\n'
                '        })\n'
            )
            if "Main service panel breaker" in src:
                print("Main breaker block already present — skipping")
            elif OLD_FUSE_END in src:
                src = src.replace(OLD_FUSE_END, NEW_FUSE_END)
                print("✅ Added main breaker BOM entry")
            else:
                print("⚠️  Could not find fuse block end — checking if fuse block exists at all:")
                print("  'Fuses (inside fused' in src:", "Fuses (inside fused" in src)

            t["config"]["source_code"] = src
            try:
                ast.parse(src)
                print("✅ calculate_solar_bom syntax OK")
            except SyntaxError as e:
                print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
                lines = src.splitlines()
                for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
                    print(f"  {i+1}: {repr(lines[i])}")
                conn.close()
                raise SystemExit(1)

    # ── 2. extract_pdf_data: extend JSON params block ─────────────────────────
    if name == "pdf_extractor":
        for t in tools:
            if t["config"]["name"] != "extract_pdf_data":
                continue
            src = t["config"]["source_code"]

            OLD_BLOCK = (
                '"fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
                '            "fuse_quantity (int number of fuses, 0=derive from strings).\\n"'
            )
            NEW_BLOCK = (
                '"fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
                '            "fuse_quantity (int number of fuses, 0=derive from strings), "\n'
                '            "pv_breaker_quantity (int number of PV breakers, usually 1 or equal to num_strings), "\n'
                '            "main_breaker_size (int amps of the main panel service breaker, 0=not found), "\n'
                '            "main_breaker_quantity (int, usually 1).\\n"'
            )
            if "main_breaker_size" in src:
                print("extract_pdf_data JSON block already has main_breaker_size — skipping")
            elif OLD_BLOCK in src:
                src = src.replace(OLD_BLOCK, NEW_BLOCK)
                t["config"]["source_code"] = src
                try:
                    ast.parse(src)
                    print("✅ extract_pdf_data JSON block updated + syntax OK")
                except SyntaxError as e:
                    print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
                    conn.close()
                    raise SystemExit(1)
            else:
                idx = src.find("fuse_quantity (int number")
                print("⚠️  Anchor not found. Context:", repr(src[max(0,idx-5):idx+80]))

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ All changes saved to DB.")
