"""
Adds physical AC disconnect and fuse parts to calculate_solar_bom,
and updates the extract_pdf_data JSON params block to pass those values through.

New parameters added to calculate_solar_bom:
  disconnect_size     : int   - AC disconnect amperage (e.g. 30, 60)
  disconnect_quantity : int   - number of disconnects (usually 1)
  disconnect_brand    : str   - brand label (e.g. "Square D", "Eaton")
  fuse_size           : int   - fuse amperage inside fused disconnect (e.g. 15, 20)
  fuse_quantity       : int   - number of fuses (0 = derive from strings)
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

    # ── 1. calculate_solar_bom: add disconnect/fuse params + BOM entries ──────
    if name == "bom_calculator":
        for t in tools:
            if t["config"]["name"] != "calculate_solar_bom":
                continue
            src = t["config"]["source_code"]

            # a) Add new parameters after pv_breaker_size
            OLD_SIG = "    pv_breaker_size: int = 0,\n) -> str:"
            NEW_SIG  = (
                "    pv_breaker_size: int = 0,\n"
                "    disconnect_size: int = 0,\n"
                "    disconnect_quantity: int = 1,\n"
                "    disconnect_brand: str = \"\",\n"
                "    fuse_size: int = 0,\n"
                "    fuse_quantity: int = 0,\n"
                ") -> str:"
            )
            if "disconnect_size" in src:
                print("calculate_solar_bom params already patched — skipping sig")
            elif OLD_SIG in src:
                src = src.replace(OLD_SIG, NEW_SIG)
                print("✅ Added disconnect/fuse params to calculate_solar_bom signature")
            else:
                print("⚠️  Could not find signature anchor in calculate_solar_bom!")
                continue

            # b) Add docstring lines for new params
            OLD_DOC = "        has_fused_disconnect: True = fused AC disconnect present (changes electrical BOM)\n        pv_breaker_size:      PV breaker amps (used only if has_fused_disconnect=False)"
            NEW_DOC = (
                "        has_fused_disconnect: True = fused AC disconnect present (changes electrical BOM)\n"
                "        pv_breaker_size:      PV breaker amps (used only if has_fused_disconnect=False)\n"
                "        disconnect_size:      AC disconnect amperage (e.g. 30, 60) — 0 = not specified\n"
                "        disconnect_quantity:  Number of AC disconnects (default 1)\n"
                "        disconnect_brand:     Brand label for the order sheet\n"
                "        fuse_size:            Fuse amperage inside fused disconnect (e.g. 15, 20)\n"
                "        fuse_quantity:        Number of fuses (0 = derive from num_strings)"
            )
            if OLD_DOC in src:
                src = src.replace(OLD_DOC, NEW_DOC)
                print("✅ Updated docstring")

            # c) Inject disconnect + fuse BOM items into electrical_bom section
            # Insert right after the closing ']' of the has_fused_disconnect block
            OLD_ELEC_END = (
                "    else:\n"
                "        if pv_breaker_size > 0:\n"
                "            electrical_bom = [\n"
                "                {\"description\": f\"{pv_breaker_size}A/2P PV Interconnect Breaker\",\n"
                "                 \"part_number\": f\"BR{pv_breaker_size}\",  \"qty\": 1,  \"unit\": \"EA\"},\n"
                "            ]\n"
            )
            NEW_ELEC_END = (
                "    else:\n"
                "        if pv_breaker_size > 0:\n"
                "            electrical_bom = [\n"
                "                {\"description\": f\"{pv_breaker_size}A/2P PV Interconnect Breaker\",\n"
                "                 \"part_number\": f\"BR{pv_breaker_size}\",  \"qty\": 1,  \"unit\": \"EA\"},\n"
                "            ]\n"
                "\n"
                "    # ── Physical AC disconnect unit ───────────────────────────────────────────\n"
                "    if disconnect_size > 0:\n"
                "        disc_brand_label = f\" ({disconnect_brand})\" if disconnect_brand else \"\"\n"
                "        disc_pn = f\"DISC-{disconnect_size}A\"\n"
                "        electrical_bom.append({\n"
                "            \"description\": f\"{disconnect_size}A AC Disconnect Switch{disc_brand_label}\",\n"
                "            \"part_number\": disc_pn,\n"
                "            \"qty\": max(disconnect_quantity, 1),\n"
                "            \"unit\": \"EA\",\n"
                "        })\n"
                "\n"
                "    # ── Fuses (inside fused disconnect or separate combiner) ───────────────\n"
                "    if fuse_size > 0:\n"
                "        actual_fuse_qty = fuse_quantity if fuse_quantity > 0 else strings * 2\n"
                "        electrical_bom.append({\n"
                "            \"description\": f\"{fuse_size}A Cartridge Fuse (for fused disconnect)\",\n"
                "            \"part_number\": f\"FUSE-{fuse_size}A\",\n"
                "            \"qty\": actual_fuse_qty,\n"
                "            \"unit\": \"EA\",\n"
                "        })\n"
            )
            if "Physical AC disconnect unit" in src:
                print("Disconnect BOM entries already present — skipping")
            elif OLD_ELEC_END in src:
                src = src.replace(OLD_ELEC_END, NEW_ELEC_END)
                print("✅ Added AC disconnect + fuse BOM entries")
            else:
                print("⚠️  Could not find electrical_bom insertion point!")

            t["config"]["source_code"] = src
            # Verify syntax
            try:
                ast.parse(src)
                print("✅ calculate_solar_bom syntax OK")
            except SyntaxError as e:
                print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
                raise SystemExit(1)

    # ── 2. extract_pdf_data: add new fields to the JSON params block ──────────
    if name == "pdf_extractor":
        for t in tools:
            if t["config"]["name"] != "extract_pdf_data":
                continue
            src = t["config"]["source_code"]

            OLD_JSON_BLOCK = (
                '"has_fused_disconnect (boolean), "\n'
                '            "pv_breaker_size (int amps, 0=none).\\n"'
            )
            NEW_JSON_BLOCK = (
                '"has_fused_disconnect (boolean), "\n'
                '            "pv_breaker_size (int amps, 0=none), "\n'
                '            "disconnect_size (int amps of AC disconnect unit, 0=not found), "\n'
                '            "disconnect_quantity (int, usually 1), "\n'
                '            "disconnect_brand (string, brand name or empty string), "\n'
                '            "fuse_size (int amps per fuse inside disconnect or combiner, 0=none), "\n'
                '            "fuse_quantity (int number of fuses, 0=derive from strings).\\n"'
            )

            if "disconnect_size" in src:
                print("extract_pdf_data JSON block already has disconnect_size — skipping")
            elif OLD_JSON_BLOCK in src:
                src = src.replace(OLD_JSON_BLOCK, NEW_JSON_BLOCK)
                t["config"]["source_code"] = src
                print("✅ Updated extract_pdf_data JSON params block with disconnect/fuse fields")
                try:
                    ast.parse(src)
                    print("✅ extract_pdf_data syntax OK")
                except SyntaxError as e:
                    print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
                    raise SystemExit(1)
            else:
                print("⚠️  Could not find JSON block anchor in extract_pdf_data — check source!")

    # ── 3. bom_calculator system message: mention new params ─────────────────
    if name == "bom_calculator":
        sys_msg = p["config"].get("system_message", "")
        if "disconnect_size" not in sys_msg:
            p["config"]["system_message"] = sys_msg.rstrip() + (
                "\n\nThe JSON block from pdf_extractor may also include: "
                "disconnect_size, disconnect_quantity, disconnect_brand, fuse_size, fuse_quantity. "
                "Pass ALL of these to calculate_solar_bom as well."
            )
            print("✅ Updated bom_calculator system message")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ All changes saved to DB.")
