"""
Makes the bom_calculator much more explicit about passing ALL electrical params
from the JSON block to calculate_solar_bom, including disconnect_size.
Also updates the calculate_solar_bom tool description's ELECTRICAL section.
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    name = p["config"]["name"]

    # ── 1. Stronger bom_calculator system message ─────────────────────────────
    if name == "bom_calculator":
        p["config"]["system_message"] = (
            "You are the Solar BOM calculator. Your ONLY job is to calculate the bill of materials.\n\n"
            "Step 1: Call lookup_similar_jobs once with customer name/address and inverter_system.\n\n"
            "Step 2: The pdf_extractor output ends with a ```json code block. "
            "Extract EVERY field from that JSON block and call calculate_solar_bom. "
            "Pass ALL fields exactly as they appear — do NOT omit any field, do NOT substitute defaults "
            "when a value is given in the JSON.\n\n"
            "CRITICAL — you MUST pass these electrical fields if they are non-zero in the JSON:\n"
            "  disconnect_size, disconnect_quantity, disconnect_brand,\n"
            "  fuse_size, fuse_quantity,\n"
            "  pv_breaker_size, pv_breaker_quantity,\n"
            "  main_breaker_size, main_breaker_quantity,\n"
            "  has_fused_disconnect\n\n"
            "Step 3: Output ONLY the raw BOM JSON returned by calculate_solar_bom. "
            "No commentary, no summary. Do NOT say TERMINATE. "
            "The next agent handles the order sheet."
        )
        print("✅ Updated bom_calculator system message")

    # ── 2. Update calculate_solar_bom ELECTRICAL docstring section ────────────
    if name == "bom_calculator":
        for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
            if t["config"]["name"] != "calculate_solar_bom":
                continue
            src = t["config"]["source_code"]

            OLD_ELEC_DOC = (
                "    ELECTRICAL (has_fused_disconnect):\n"
                "      True  → no PV interconnect breaker; add 15A/2P combiner breaker (1 per job)\n"
                "               + 20A Eaton BR 2-pole breaker per string (num_strings or 1 if unset)\n"
                "      False → add PV breaker at pv_breaker_size amps if provided\n"
            )
            NEW_ELEC_DOC = (
                "    ELECTRICAL (has_fused_disconnect):\n"
                "      True  → no PV interconnect breaker; add 15A/2P combiner breaker (1 per job)\n"
                "               + 20A Eaton BR 2-pole breaker per string (num_strings or 1 if unset)\n"
                "      False → add PV breaker at pv_breaker_size amps if provided\n\n"
                "    AC DISCONNECT (always include if disconnect_size > 0):\n"
                "      disconnect_size     — amperage of the physical AC disconnect unit (e.g. 30, 60)\n"
                "      disconnect_quantity — number of disconnect units (default 1)\n"
                "      disconnect_brand    — brand label for the order (e.g. Square D, Eaton)\n"
                "      fuse_size           — fuse amps inside a fused disconnect (0 = not fused)\n"
                "      fuse_quantity       — number of fuses (0 = derive from strings)\n"
                "      IMPORTANT: disconnect_size applies to the physical disconnect box, regardless\n"
                "                 of whether it is fused or not. Always add it to the BOM if > 0.\n"
            )
            if "AC DISCONNECT (always include" in src:
                print("ELECTRICAL doc already updated — skipping")
            elif OLD_ELEC_DOC in src:
                src = src.replace(OLD_ELEC_DOC, NEW_ELEC_DOC)
                t["config"]["source_code"] = src
                try:
                    ast.parse(src)
                    print("✅ Updated calculate_solar_bom ELECTRICAL docstring + syntax OK")
                except SyntaxError as e:
                    print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
                    conn.close()
                    raise SystemExit(1)
            else:
                print("⚠️  Could not find ELECTRICAL doc anchor")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ Saved to DB.")
