"""
Comprehensive fix based on the electrical diagram screenshot.

(N) = New → MUST appear on BOM
(E) = Existing → MUST be skipped

New items identified in diagram:
  1. (N) Combiner Box  - e.g. Q.CELL Q HOME COMBINER 80 G1, 125A
  2. (N) Junction Boxes - 600V NEMA 3R (may appear multiple times → count them)
  3. (N) PV Load Center / MLO Panel - 125A NEMA 3R
  4. (N) AC Disconnect NON-FUSIBLE - 200A, 240V NEMA 3R (disconnect_size)
  5. (N) Service Rated AC Disconnect FUSED - 200A, (2) 125A fuses (fused_disconnect_*)

Existing items (skip):
  - (E) Bi-directional utility meter
  - (E) Main breaker (in existing panel)
  - (E) Main service panel

Changes:
  A. calculate_solar_bom → add fused_disconnect_size/fuse params, junction_boxes,
     pv_load_center_size, combiner_box_model
  B. extract_pdf_data → rewrite page 4 vision prompt to capture (N)/(E) correctly
  C. extract_pdf_data → add new JSON block fields
  D. bom_calculator system message → list ALL new fields in CRITICAL section
"""
import sqlite3, json, ast, re

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# ─────────────────────────────────────────────────────────────────────────────
# PART A: update calculate_solar_bom
# ─────────────────────────────────────────────────────────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "calculate_solar_bom":
            continue
        src = t["config"]["source_code"]

        # ── A1. Extend function signature ──
        OLD_SIG_END = "    main_breaker_quantity: int = 1,\n) -> str:"
        NEW_SIG_END = (
            "    main_breaker_quantity: int = 1,\n"
            "    fused_disconnect_size: int = 0,\n"
            "    fused_disconnect_fuse_size: int = 0,\n"
            "    fused_disconnect_fuse_quantity: int = 0,\n"
            "    junction_box_quantity: int = 0,\n"
            "    pv_load_center_size: int = 0,\n"
            "    combiner_box_model: str = \"\",\n"
            ") -> str:"
        )
        if "fused_disconnect_size" in src:
            print("Signature already has fused_disconnect_size — skipping A1")
        elif OLD_SIG_END in src:
            src = src.replace(OLD_SIG_END, NEW_SIG_END)
            print("✅ A1: Extended function signature")
        else:
            print("⚠️  A1: Could not find signature anchor")

        # ── A2. Update docstring ELECTRICAL section to mention new fields ───
        OLD_ELEC_DOCNOTE = (
            "    IMPORTANT: disconnect_size applies to the physical disconnect box, regardless\n"
            "                 of whether it is fused or not. Always add it to the BOM if > 0.\n"
        )
        NEW_ELEC_DOCNOTE = (
            "    IMPORTANT: disconnect_size applies to the physical disconnect box, regardless\n"
            "                 of whether it is fused or not. Always add it to the BOM if > 0.\n\n"
            "    FUSED SERVICE DISCONNECT (always include if fused_disconnect_size > 0):\n"
            "      fused_disconnect_size      — amps of the fused service-rated AC disconnect\n"
            "      fused_disconnect_fuse_size — amps per fuse (e.g. 125)\n"
            "      fused_disconnect_fuse_quantity — number of fuses (e.g. 2)\n\n"
            "    ADDITIONAL (N) EQUIPMENT:\n"
            "      combiner_box_model   — model string of combiner box, e.g. 'Q.CELL Q HOME COMBINER 80 G1'\n"
            "      junction_box_quantity — count of (N) junction boxes (600V NEMA 3R)\n"
            "      pv_load_center_size  — amps of MLO PV load center / sub-panel (e.g. 125)\n"
        )
        if "FUSED SERVICE DISCONNECT" in src:
            print("Docstring already updated — skipping A2")
        elif OLD_ELEC_DOCNOTE in src:
            src = src.replace(OLD_ELEC_DOCNOTE, NEW_ELEC_DOCNOTE)
            print("✅ A2: Updated docstring")
        else:
            print("⚠️  A2: Could not find docstring anchor")

        # ── A3. Add BOM entries for new items ──────────────────────────────
        # Find the block that adds main_breaker to BOM, then append after it
        OLD_MAIN_BR_BLOCK = (
            "    if main_breaker_size > 0:\n"
            "        electrical_bom.append({\n"
            "            \"item\": f\"MAIN-BR{main_breaker_size}\",\n"
            "            \"description\": f\"{main_breaker_size}A Main Panel Breaker\",\n"
            "            \"qty\": main_breaker_quantity,\n"
            "            \"unit\": \"ea\",\n"
            "        })\n"
        )
        NEW_MAIN_BR_BLOCK = (
            "    if main_breaker_size > 0:\n"
            "        electrical_bom.append({\n"
            "            \"item\": f\"MAIN-BR{main_breaker_size}\",\n"
            "            \"description\": f\"{main_breaker_size}A Main Panel Breaker\",\n"
            "            \"qty\": main_breaker_quantity,\n"
            "            \"unit\": \"ea\",\n"
            "        })\n"
            "\n"
            "    # Fused service-rated AC disconnect (separate unit from non-fused disconnect)\n"
            "    if fused_disconnect_size > 0:\n"
            "        fuse_desc = \"\"\n"
            "        if fused_disconnect_fuse_size > 0 and fused_disconnect_fuse_quantity > 0:\n"
            "            fuse_desc = f\", ({fused_disconnect_fuse_quantity}) {fused_disconnect_fuse_size}A Fuses\"\n"
            "        elif fused_disconnect_fuse_size > 0:\n"
            "            fuse_desc = f\", {fused_disconnect_fuse_size}A Fuses\"\n"
            "        electrical_bom.append({\n"
            "            \"item\": f\"DISC-FUSED-{fused_disconnect_size}A\",\n"
            "            \"description\": f\"{fused_disconnect_size}A Service Rated Fused AC Disconnect{fuse_desc}, 240V NEMA 3R\",\n"
            "            \"qty\": 1,\n"
            "            \"unit\": \"ea\",\n"
            "        })\n"
            "\n"
            "    # Combiner box (e.g. Q.CELL Q HOME COMBINER 80 G1)\n"
            "    if combiner_box_model:\n"
            "        electrical_bom.append({\n"
            "            \"item\": \"COMBINER\",\n"
            "            \"description\": f\"Combiner Box - {combiner_box_model}, NEMA 3R, UL Listed\",\n"
            "            \"qty\": 1,\n"
            "            \"unit\": \"ea\",\n"
            "        })\n"
            "\n"
            "    # Junction boxes (600V NEMA 3R)\n"
            "    if junction_box_quantity > 0:\n"
            "        electrical_bom.append({\n"
            "            \"item\": \"JBOX-600V\",\n"
            "            \"description\": \"600V NEMA 3R Junction Box, UL Listed\",\n"
            "            \"qty\": junction_box_quantity,\n"
            "            \"unit\": \"ea\",\n"
            "        })\n"
            "\n"
            "    # PV Load Center / MLO sub-panel\n"
            "    if pv_load_center_size > 0:\n"
            "        electrical_bom.append({\n"
            "            \"item\": f\"PV-LC-{pv_load_center_size}A\",\n"
            "            \"description\": f\"{pv_load_center_size}A MLO PV Load Center (Sub-Panel), NEMA 3R, UL Listed\",\n"
            "            \"qty\": 1,\n"
            "            \"unit\": \"ea\",\n"
            "        })\n"
        )
        if "DISC-FUSED" in src:
            print("BOM entries already added — skipping A3")
        elif OLD_MAIN_BR_BLOCK in src:
            src = src.replace(OLD_MAIN_BR_BLOCK, NEW_MAIN_BR_BLOCK)
            print("✅ A3: Added BOM entries for new (N) items")
        else:
            print("⚠️  A3: Could not find main_breaker BOM block")

        try:
            ast.parse(src)
            print("✅ Syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)

        t["config"]["source_code"] = src

# ─────────────────────────────────────────────────────────────────────────────
# PART B + C: update extract_pdf_data (vision prompt + JSON block)
# ─────────────────────────────────────────────────────────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        # ── B. Replace vision prompt for page 4 ────────────────────────────
        OLD_VISION_PROMPT = (
            '"Analyze it carefully and extract ONLY the following — be concise:\\n\\n"\n'
            '                        "DISCONNECT:\\n"\n'
            '                        "- disconnect_type = <AC disconnect | fused disconnect | combined disconnect>\\n"\n'
            '                        "- disconnect_size = <amperage, e.g. 30A, 60A>\\n"\n'
            '                        "- disconnect_brand = <brand if visible, e.g. Eaton, Square D, Siemens>\\n"\n'
            '                        "- disconnect_poles = <SPST / DPST / 2-pole / etc.>\\n\\n"\n'
            '                        "FUSING (if present):\\n"\n'
            '                        "- has_fused_disconnect = True or False\\n"\n'
            '                        "- fuse_size = <amperage per fuse, e.g. 15A, 20A>  (or \'none\')\\n"\n'
            '                        "- fuse_type = <cartridge / blade / other>  (or \'none\')\\n\\n"\n'
            '                        "INTERCONNECTION:\\n"\n'
            '                        "- interconnection_method = <load side tap | line side tap | supply side | meter socket | utility backfeed>\\n"\n'
            '                        "- pv_breaker_size = <amperage of the PV breaker in the main panel, e.g. 30A>  (or \'none\')\\n"\n'
            '                        "- main_panel_size = <service amps, e.g. 200A>\\n"\n'
            '                        "- main_breaker_size = <e.g. 200A>\\n"\n'
            '                        "- num_strings = <number of DC string circuits shown>\\n\\n"\n'
            '                        "Use only the labels above. If a field is not shown in the diagram, write \'not shown\'."'
        )
        NEW_VISION_PROMPT = (
            '"Analyze this electrical single-line diagram carefully.\\n\\n"\n'
            '                        "IMPORTANT RULES:\\n"\n'
            '                        "- Items labeled (N) = NEW — must be listed.\\n"\n'
            '                        "- Items labeled (E) = EXISTING — skip entirely, do NOT list them.\\n\\n"\n'
            '                        "Extract EACH of the following categories for (N) items only:\\n\\n"\n'
            '                        "NON-FUSED AC DISCONNECT (look for label containing NON-FUSIBLE or NON-FUSED):\\n"\n'
            '                        "- disconnect_size = <integer amps, e.g. 200>  (0 if not found)\\n"\n'
            '                        "- disconnect_brand = <brand name or empty>\\n\\n"\n'
            '                        "FUSED SERVICE RATED AC DISCONNECT (look for label containing FUSED and a fuse size):\\n"\n'
            '                        "- fused_disconnect_size = <integer amps, e.g. 200>  (0 if not found)\\n"\n'
            '                        "- fused_disconnect_fuse_size = <fuse amps, e.g. 125>  (0 if not found)\\n"\n'
            '                        "- fused_disconnect_fuse_quantity = <number of fuses, e.g. 2>  (0 if not found)\\n\\n"\n'
            '                        "COMBINER BOX (look for label containing COMBINER):\\n"\n'
            '                        "- combiner_box_model = <full model name as labeled, e.g. Q.CELL Q HOME COMBINER 80 G1>  (empty if not found)\\n\\n"\n'
            '                        "JUNCTION BOXES (look for labels containing JUNCTION BOX):\\n"\n'
            '                        "- junction_box_quantity = <count of (N) junction boxes shown>  (0 if none)\\n\\n"\n'
            '                        "PV LOAD CENTER / MLO PANEL (look for label containing LOAD CENTER or MLO):\\n"\n'
            '                        "- pv_load_center_size = <integer amps, e.g. 125>  (0 if not found)\\n\\n"\n'
            '                        "INTERCONNECTION:\\n"\n'
            '                        "- interconnection_method = <load side tap | line side tap | supply side | meter socket | utility backfeed>\\n"\n'
            '                        "- pv_breaker_size = <amperage of the PV breaker at point of interconnect, e.g. 80>  (0 if none)\\n"\n'
            '                        "- num_strings = <number of DC string circuits shown>\\n\\n"\n'
            '                        "FUSING — for has_fused_disconnect field only:\\n"\n'
            '                        "- has_fused_disconnect = True if a fused disconnect exists, False otherwise\\n\\n"\n'
            '                        "Output only the labeled fields above. If a field is not shown, use 0 or empty string."'
        )
        if "NON-FUSED AC DISCONNECT" in src:
            print("Vision prompt already updated — skipping B")
        elif OLD_VISION_PROMPT in src:
            src = src.replace(OLD_VISION_PROMPT, NEW_VISION_PROMPT)
            print("✅ B: Updated page 4 vision prompt")
        else:
            print("⚠️  B: Could not find vision prompt anchor — trying partial match")
            # partial match on beginning
            partial = '"Analyze it carefully and extract ONLY the following'
            if partial in src:
                # find end of vision prompt block
                i = src.find(partial)
                j = src.find('"Use only the labels above.', i)
                if j != -1:
                    j = src.find('"', j+1)  # closing quote of that string
                    j = src.find('\n', j)    # end of that line
                    old_block = src[i:j+1]
                    replace_with = NEW_VISION_PROMPT
                    src = src[:i] + replace_with + src[j+1:]
                    print("✅ B (partial): Updated page 4 vision prompt")
                else:
                    print("⚠️  B: Could not find end of vision block")
            else:
                print("⚠️  B: Vision prompt not found at all")

        # ── C. Update JSON params block ─────────────────────────────────────
        OLD_JSON_BLOCK = (
            '"main_breaker_size (int amps of the main panel service breaker e.g. 200, 0=not found), "\n'
            '            "main_breaker_quantity (int, usually 1).\\n"\n'
            '            "panel_count MUST match the actual installed panel count.'
        )
        NEW_JSON_BLOCK = (
            '"main_breaker_size (int amps of the main panel service breaker e.g. 200, 0=not found), "\n'
            '            "main_breaker_quantity (int, usually 1), "\n'
            '            "fused_disconnect_size (int amps of the fused service-rated AC disconnect, 0=not found), "\n'
            '            "fused_disconnect_fuse_size (int amps per fuse inside fused disconnect, e.g. 125, 0=not found), "\n'
            '            "fused_disconnect_fuse_quantity (int number of fuses in fused disconnect, e.g. 2, 0=not found), "\n'
            '            "junction_box_quantity (int count of (N) junction boxes, 0=none), "\n'
            '            "pv_load_center_size (int amps of the (N) MLO PV load center / sub-panel, 0=not found), "\n'
            '            "combiner_box_model (string full model name of (N) combiner box, empty if none).\\n"\n'
            '            "RULE: Only include (N) New items. Skip all (E) Existing items.\\n"\n'
            '            "panel_count MUST match the actual installed panel count.'
        )
        if "fused_disconnect_size" in src and "junction_box_quantity" in src:
            print("JSON block already updated — skipping C")
        elif OLD_JSON_BLOCK in src:
            src = src.replace(OLD_JSON_BLOCK, NEW_JSON_BLOCK)
            print("✅ C: Updated JSON params block")
        else:
            # Try alternate endings
            alt_old = (
                '"main_breaker_quantity (int, usually 1).\\n"\n'
                '            "panel_count MUST match the actual installed panel count.'
            )
            if alt_old in src:
                alt_new = (
                    '"main_breaker_quantity (int, usually 1), "\n'
                    '            "fused_disconnect_size (int amps of the fused service-rated AC disconnect, 0=not found), "\n'
                    '            "fused_disconnect_fuse_size (int amps per fuse inside fused disconnect, e.g. 125, 0=not found), "\n'
                    '            "fused_disconnect_fuse_quantity (int number of fuses in fused disconnect, e.g. 2, 0=not found), "\n'
                    '            "junction_box_quantity (int count of (N) junction boxes, 0=none), "\n'
                    '            "pv_load_center_size (int amps of the (N) MLO PV load center / sub-panel, 0=not found), "\n'
                    '            "combiner_box_model (string full model name of (N) combiner box, empty if none).\\n"\n'
                    '            "RULE: Only include (N) New items. Skip all (E) Existing items.\\n"\n'
                    '            "panel_count MUST match the actual installed panel count.'
                )
                src = src.replace(alt_old, alt_new)
                print("✅ C (alt): Updated JSON params block")
            else:
                print("⚠️  C: Could not update JSON block")

        try:
            ast.parse(src)
            print("✅ Syntax OK for extract_pdf_data")
        except SyntaxError as e:
            print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)

        t["config"]["source_code"] = src

# ─────────────────────────────────────────────────────────────────────────────
# PART D: bom_calculator system message (add new fields to CRITICAL list)
# ─────────────────────────────────────────────────────────────────────────────
for p in data["config"]["participants"]:
    if p["config"]["name"] != "bom_calculator":
        continue
    OLD_CRITICAL = (
        "CRITICAL — you MUST pass these electrical fields if they are non-zero in the JSON:\n"
        "  disconnect_size, disconnect_quantity, disconnect_brand,\n"
        "  fuse_size, fuse_quantity,\n"
        "  pv_breaker_size, pv_breaker_quantity,\n"
        "  main_breaker_size, main_breaker_quantity,\n"
        "  has_fused_disconnect\n"
    )
    NEW_CRITICAL = (
        "CRITICAL — you MUST pass these electrical fields if they are non-zero in the JSON:\n"
        "  disconnect_size, disconnect_quantity, disconnect_brand,\n"
        "  fuse_size, fuse_quantity,\n"
        "  pv_breaker_size, pv_breaker_quantity,\n"
        "  main_breaker_size, main_breaker_quantity,\n"
        "  has_fused_disconnect,\n"
        "  fused_disconnect_size, fused_disconnect_fuse_size, fused_disconnect_fuse_quantity,\n"
        "  junction_box_quantity, pv_load_center_size, combiner_box_model\n"
    )
    msg = p["config"]["system_message"]
    if "fused_disconnect_size" in msg:
        print("bom_calculator system message already updated — skipping D")
    elif OLD_CRITICAL in msg:
        p["config"]["system_message"] = msg.replace(OLD_CRITICAL, NEW_CRITICAL)
        print("✅ D: Updated bom_calculator system message")
    else:
        print("⚠️  D: Could not find CRITICAL anchor in system message")

# ─────────────────────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────────────────────
cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\n✅ All changes saved to DB.")
