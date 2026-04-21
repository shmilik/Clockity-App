"""
Fixes two problems with the Solar BOM team:
1. extract_pdf_data Claude prompt now outputs a ```json params block at the end
   containing the exact parameters for calculate_solar_bom (panel_count, etc.)
2. bom_calculator system message is updated to read that JSON block directly
   instead of trying to guess values from free text.

This fixes: few line items, wrong panel count, missing sections.
"""

import sqlite3, json, re

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"

# ── Suffix to append to the Claude parsing prompt in extract_pdf_data ─────────
# This goes right before the PDF TEXT section.
JSON_PARAMS_INSTRUCTION = (
    "\n\nAt the very end of your response, output a ```json code block containing "
    "the EXACT parameter values to pass to calculate_solar_bom. "
    "Use these exact keys — do NOT omit any key:\n\n"
    "```json\n"
    '{\n'
    '  "panel_count": <total panels as integer>,\n'
    '  "panel_orientation": "<portrait or landscape>",\n'
    '  "panels_per_row": <integer — panels in one horizontal row>,\n'
    '  "panel_width_in": <short-side width in inches — use 40.9 if unknown>,\n'
    '  "panel_height_in": <long-side height in inches — use 67.9 if unknown>,\n'
    '  "inverter_count": <integer — use 0 to mean 1 microinverter per panel>,\n'
    '  "inverter_system": "<enphase_iq | qcells_integrated | hoymiles | solaredge | string | string_central>",\n'
    '  "rail_system": "<IronRidge XR10 | IronRidge XR100 | IronRidge QM ClickFit | Unirac SolarMount>",\n'
    '  "rail_length_ft": <float — default 14.0 if not stated>,\n'
    '  "roof_attachment": "<comp_shingle | tile | metal_standing_seam | flat>",\n'
    '  "mounting_foot_count": <integer — use 0 if not found, tool uses formula>,\n'
    '  "num_strings": <integer — number of DC strings, use 0 if unknown>,\n'
    '  "override_sticks": <integer — rail stick count from schedule, use 0 if not found>,\n'
    '  "override_splices": <integer — splice kit count from schedule, use 0 if not found>,\n'
    '  "has_fused_disconnect": <true or false>,\n'
    '  "pv_breaker_size": <PV breaker amps as integer, use 0 if fused disconnect or unknown>\n'
    '}\n'
    '```\n\n'
    "Rules: Use 0 for unknown integers, false for unknown booleans. "
    "panel_count MUST be the actual number of panels on the roof — count carefully from the layout."
)

# ── New bom_calculator system message ─────────────────────────────────────────
NEW_BOM_CALC_SYS = (
    "You are the Solar BOM calculator. Your ONLY job is to calculate the bill of materials.\n\n"
    "Step 1: Call lookup_similar_jobs once. Use the customer name/address and inverter_system "
    "from the extracted data.\n\n"
    "Step 2: The pdf_extractor output ends with a ```json code block. "
    "Extract ALL fields from that JSON block and call calculate_solar_bom using those exact values. "
    "Do NOT guess or substitute defaults when a value is given in the JSON. "
    "Copy the JSON values directly into the function call arguments.\n\n"
    "Step 3: Output ONLY the raw BOM JSON returned by calculate_solar_bom — no commentary, "
    "no summary, no mention of order sheets or Excel. "
    "Do NOT say the order sheet was generated. Do NOT say TERMINATE. "
    "Your job ends after outputting the BOM JSON. The next agent handles the sheet."
)


def patch():
    conn = sqlite3.connect(DB)
    cur  = conn.cursor()
    cur.execute("SELECT component FROM team WHERE id=4")
    data = json.loads(cur.fetchone()[0])

    changed = False

    for p in data["config"]["participants"]:
        name = p["config"]["name"]

        # ── 1. extract_pdf_data: inject JSON params instruction into Claude prompt ──
        if name == "pdf_extractor":
            tools = p["config"]["workbench"]["config"]["tools"]
            for t in tools:
                if t["config"]["name"] == "extract_pdf_data":
                    src = t["config"]["source_code"]

                    # Find the insertion point: right before the final f"PDF TEXT:\n{combined_text..."
                    marker = "Keep answers concise. Use the exact labels above so the BOM Calculator can parse them."
                    suffix_marker  = "At the very end of your response, output a ```json code block"

                    if suffix_marker in src:
                        print("JSON params instruction already present — skipping extract_pdf_data patch")
                    elif marker in src:
                        src = src.replace(
                            marker,
                            marker + JSON_PARAMS_INSTRUCTION
                        )
                        t["config"]["source_code"] = src
                        print("✅ Patched extract_pdf_data — JSON params block added to Claude prompt")
                        changed = True
                    else:
                        print("⚠️  Could not find insertion marker in extract_pdf_data — check source!")

        # ── 2. bom_calculator: replace system message ──────────────────────────────
        if name == "bom_calculator":
            old_sys = p["config"].get("system_message", "")
            if "```json code block" in old_sys:
                print("bom_calculator system message already patched — skipping")
            else:
                p["config"]["system_message"] = NEW_BOM_CALC_SYS
                print("✅ Patched bom_calculator system message")
                changed = True

    if changed:
        cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
        conn.commit()
        print("✅ Changes saved to DB.")
    else:
        print("No changes made.")

    conn.close()


if __name__ == "__main__":
    patch()
