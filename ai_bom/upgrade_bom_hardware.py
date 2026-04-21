"""
Upgrades the Solar BOM Team with corrected hardware logic:

CLAMP FIX:
  - Between each panel: 2 mid clamps (1 per rail, top + bottom)
  - At each row end: 2 end clamps per rail-end (4 total per row: 2 on left, 2 on right)
  - Formula: mids = 2*(panels_per_row-1)*rows,  ends = 4*rows

RAIL STICK LENGTH:
  - Changed default from 10ft to 14ft (168in) per real job standard

MOUNTING FOOT COUNT:
  - New arg `mounting_foot_count` (from vision blue-dot count) overrides formula if provided

MANUFACTURER CABLE/CONNECTOR SYSTEMS:
  - inverter_system arg selects the right cable/connector BOM:
    "qcells_integrated" → Q.CELLS AC daisy-chain cable + Q.CELLS trunk connectors
    "enphase_iq"        → Enphase Q-Cable trunk cable + tap connectors + terminator caps
    "hoymiles"          → Hoymiles MC4 Y-connectors + DC trunk cable
    "solaredge"         → SolarEdge P-series MC4 lead cables + AC combiner
    "string"            → MC4 connectors (1 pair per panel-to-panel connection)
    "string_central"    → MC4 connectors + DC home-run cables

RAIL SYSTEMS ADDED:
  - IronRidge QM ClickFit (the Hays St job uses this)

VISION PROMPT UPDATE:
  - Instructs Claude to count blue dots = mounting feet
  - Instructs Claude to identify inverter system type for connector selection
"""
import sqlite3, json

DB_PATH = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, component FROM team WHERE id=4")
team_id, component_json = c.fetchone()
team = json.loads(component_json)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  NEW calculate_solar_bom                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
NEW_BOM_CALC_SOURCE = r'''
def calculate_solar_bom(
    panel_count: int,
    panel_orientation: str,
    panels_per_row: int,
    panel_width_in: float = 40.9,
    panel_height_in: float = 67.9,
    inverter_count: int = 0,
    inverter_system: str = "string",
    rail_system: str = "IronRidge XR100",
    rail_length_ft: float = 14.0,
    roof_attachment: str = "comp_shingle",
    mounting_foot_count: int = 0,
) -> str:
    """Calculate a detailed solar installation Bill of Materials with part numbers.

    CLAMP RULES (actual field standard):
      Between each adjacent panel pair: 2 mid clamps (1 top rail + 1 bottom rail)
      At each row end (left + right sides): 2 end clamps per end (1 top + 1 bottom)
        → mids = 2 * (panels_per_row - 1) * num_rows
        → ends = 4 * num_rows

    MOUNTING FEET:
      If mounting_foot_count > 0, that value (from vision blue-dot count) is used.
      Otherwise: foot spacing pattern (1st @12in from edge, 2nd @+24in, then every +48in).
      Minimum 2 feet per rail. 1 foot per row end within 6in = auto included.

    RAIL:
      rail_length_ft sets the stock rail stick length (default 14ft = 168in).
      Rail runs: portrait = panels_per_row * panel_width_in per row
                 landscape = panels_per_row * panel_height_in per row
      Number of sticks per row-rail = ceil(run / (rail_length_ft * 12))
      Splice kits = sticks_per_row_rail - 1 (if any)

    CONNECTOR / CABLE SYSTEM (inverter_system arg):
      qcells_integrated  Q.CELLS AC daisy-chain cable + combiner connectors
      enphase_iq         Enphase Q-Cable trunk + tap connectors + terminator caps
      hoymiles           MC4 connectors (pair per panel-to-panel gap)
      solaredge          MC4 connectors + optimizer DC leads
      string             MC4 connector pairs (1 pair per inter-panel connection)
      string_central     MC4 connector pairs + DC home-run cable

    Args:
        panel_count:         Total solar panels
        panel_orientation:   "portrait" or "landscape"
        panels_per_row:      Panels in one horizontal row
        panel_width_in:      Short-side width in inches (default 40.9)
        panel_height_in:     Long-side height in inches (default 67.9)
        inverter_count:      Microinverter override count (0 = 1 per panel)
        inverter_system:     See CONNECTOR / CABLE SYSTEM above
        rail_system:         Rail brand (IronRidge XR100, IronRidge QM ClickFit, Unirac SolarMount)
        rail_length_ft:      Stock rail stick length in feet (default 14)
        roof_attachment:     comp_shingle | tile | metal_standing_seam | flat
        mounting_foot_count: Actual foot count from vision blue-dot count (0 = use formula)

    Returns:
        JSON string: {"summary": "...", "bom": [{description, part_number, qty, unit}, ...]}
    """
    import math, json

    # ── Validation ────────────────────────────────────────────────────────────
    errs = []
    if panel_count < 1:      errs.append("panel_count must be >= 1")
    if panels_per_row < 1:   errs.append("panels_per_row must be >= 1")
    if panels_per_row > panel_count: errs.append("panels_per_row cannot exceed panel_count")
    if panel_orientation.lower() not in ("portrait", "landscape"):
        errs.append("panel_orientation must be 'portrait' or 'landscape'")
    if errs:
        return json.dumps({"error": errs})

    is_portrait = "portrait" in panel_orientation.lower()
    num_rows    = math.ceil(panel_count / panels_per_row)

    # ── Rail geometry ─────────────────────────────────────────────────────────
    # The dimension that runs along the rail (parallel to the row)
    if is_portrait:
        rail_run_in = panels_per_row * panel_width_in
    else:
        rail_run_in = panels_per_row * panel_height_in

    rail_stick_in = rail_length_ft * 12.0
    sticks_per_row_rail  = math.ceil(rail_run_in / rail_stick_in)
    splices_per_row_rail = max(sticks_per_row_rail - 1, 0)

    # Each row has 2 rails (top + bottom)
    total_rail_sticks = sticks_per_row_rail * 2 * num_rows
    total_splices     = splices_per_row_rail * 2 * num_rows

    # ── Clamps (CORRECTED) ────────────────────────────────────────────────────
    # Mid clamps: 2 per inter-panel gap × number of gaps × number of rows
    mid_clamps_per_row = 2 * max(panels_per_row - 1, 0)
    total_mid_clamps   = mid_clamps_per_row * num_rows

    # End clamps: 4 per row (2 on left rail-end + 2 on right rail-end)
    end_clamps_per_row = 4
    total_end_clamps   = end_clamps_per_row * num_rows

    # ── Mounting feet ─────────────────────────────────────────────────────────
    if mounting_foot_count > 0:
        total_feet = mounting_foot_count   # trust vision blue-dot count
        feet_per_rail = round(mounting_foot_count / (num_rows * 2), 1)
        foot_source = "vision diagram count"
    else:
        def count_feet_for_rail(rail_len_in):
            if rail_len_in <= 0:
                return 2
            positions = []
            pos = 12.0
            while True:
                if pos > rail_len_in - 12.0:
                    break
                positions.append(pos)
                pos += 24.0 if len(positions) == 1 else 48.0
            if not positions or positions[-1] < rail_len_in - 12.0:
                far = max(rail_len_in - 12.0, 12.0)
                if not positions or far - positions[-1] > 1:
                    positions.append(far)
            return max(len(positions), 2)

        feet_per_rail  = count_feet_for_rail(rail_run_in)
        total_feet     = feet_per_rail * 2 * num_rows   # 2 rails per row
        foot_source    = "formula"

    # ── Inverters ─────────────────────────────────────────────────────────────
    total_inverters = inverter_count if inverter_count > 0 else panel_count

    # ── Connector / cable system ──────────────────────────────────────────────
    inv_sys = inverter_system.lower().strip()
    cable_bom = []

    if inv_sys == "qcells_integrated":
        # Q.CELLS AC Module / Q.MI: proprietary AC daisy-chain cable between modules
        # One cable per inter-module connection, plus combiner leads
        cable_bom = [
            {"description": "Q.CELLS AC Daisy-Chain Cable (module-to-module)",
             "part_number": "QCELLS-ACCABLE", "qty": total_inverters - num_rows,   "unit": "EA"},
            {"description": "Q.CELLS Branch Circuit End Cap / Terminator",
             "part_number": "QCELLS-TERMCAP", "qty": num_rows * 2,                "unit": "EA"},
            {"description": "Q.CELLS Combiner Branch Leads",
             "part_number": "QCELLS-LEAD",    "qty": num_rows,                    "unit": "EA"},
        ]

    elif inv_sys == "enphase_iq":
        # Enphase Q-Cable trunk system: cable runs along rail, each IQ inverter taps in
        cable_bom = [
            {"description": "Enphase Q-Cable Trunk Cable (240V, per branch circuit)",
             "part_number": "Q-12-240-L-240",  "qty": num_rows,                   "unit": "EA"},
            {"description": "Enphase Q-Cable Tap Connector (1 per microinverter)",
             "part_number": "Q-CONN-TAP",       "qty": total_inverters,            "unit": "EA"},
            {"description": "Enphase Q-Cable Terminator Cap (1 per branch end)",
             "part_number": "Q-CAP-240",        "qty": num_rows,                   "unit": "EA"},
        ]

    elif inv_sys == "solaredge":
        # SolarEdge: optimizer DC leads + MC4 between optimizer and inverter
        gaps = max(panels_per_row - 1, 0) * num_rows
        cable_bom = [
            {"description": "SolarEdge Optimizer DC Lead Extension (MC4)",
             "part_number": "SE-OPTLEAD-MC4",   "qty": total_inverters,           "unit": "EA"},
            {"description": "MC4 Connector Pairs (inter-optimizer DC string)",
             "part_number": "MC4-PAIR",          "qty": gaps,                     "unit": "PAIR"},
        ]

    elif inv_sys == "hoymiles":
        gaps = max(panels_per_row - 1, 0) * num_rows
        cable_bom = [
            {"description": "MC4 Connector Pairs (Hoymiles DC string)",
             "part_number": "MC4-PAIR",          "qty": gaps + num_rows,          "unit": "PAIR"},
            {"description": "Hoymiles AC Bus Cable",
             "part_number": "HM-ACBUS",          "qty": num_rows,                 "unit": "EA"},
        ]

    elif inv_sys in ("string", "string_central"):
        # Standard string inverter: MC4 connector pair at each inter-panel connection
        gaps = max(panels_per_row - 1, 0) * num_rows
        cable_bom = [
            {"description": "MC4 Connector Pairs (1 pair per panel-to-panel DC connection)",
             "part_number": "MC4-PAIR",          "qty": gaps,                     "unit": "PAIR"},
        ]
        if inv_sys == "string_central":
            cable_bom.append({
                "description": "DC Home-Run Cable (panel string to combiner, per string)",
                "part_number": "DC-HOMERUN-10AWG", "qty": num_rows,               "unit": "EA"})
    else:
        cable_bom = [
            {"description": f"Connectors/cables ({inverter_system} — verify with manufacturer)",
             "part_number": "SEE-MFR", "qty": total_inverters, "unit": "EA"},
        ]

    # ── Part numbers ──────────────────────────────────────────────────────────
    PARTS = {
        "IronRidge XR100": {
            "rail": "XR-100-204B", "splice": "XR-100-SP",
            "mid": "CLM-0003B", "end": "CLM-0002B",
            "wire_clip": "WM-CLIP-100", "ground_lug": "GR-LUG-100",
            "t_bolt": "HS-T-BLT-0100", "screw": "HS-M8-SS",
        },
        "IronRidge QM ClickFit": {
            "rail": "QM-CF-SD-168M", "splice": "QM-CF-SPLICE",
            "mid": "QM-MIDCLAMP", "end": "QM-ENDCLAMP",
            "wire_clip": "QM-WM-CLIP", "ground_lug": "QM-GR-LUG",
            "t_bolt": "QM-CLICKER-BOLT", "screw": "QM-SS-SCREW",
        },
        "Unirac SolarMount": {
            "rail": "SM-RL-168", "splice": "SM-SPLICE",
            "mid": "SM-MC", "end": "SM-EC",
            "wire_clip": "SM-WC", "ground_lug": "SM-GL",
            "t_bolt": "SM-TBOLT", "screw": "SM-SCREW",
        },
    }
    FOOT_PARTS = {
        "comp_shingle":        "FW-LFAB-200B",
        "tile":                "FW-LFAB-TILE",
        "metal_standing_seam": "FW-LFAB-MS",
        "flat":                "FW-LFAB-FLAT",
    }

    # Try exact match, then partial match
    pn = None
    for key in PARTS:
        if key.lower() in rail_system.lower() or rail_system.lower() in key.lower():
            pn = PARTS[key]
            break
    if pn is None:
        pn = PARTS["IronRidge XR100"]

    foot_pn = FOOT_PARTS.get(roof_attachment, "FW-LFAB-200B")

    # ── Wire management & grounding ───────────────────────────────────────────
    total_wire_clips = math.ceil(panel_count / 2)
    total_ground_lugs = 2 * num_rows  # 1 per rail

    # ── Assemble BOM ──────────────────────────────────────────────────────────
    bom = [
        {"description": "Solar Panels",
         "part_number": "SEE-ENGINEERING", "qty": panel_count,       "unit": "EA"},
        {"description": f"Inverters ({inverter_system})",
         "part_number": "SEE-ENGINEERING", "qty": total_inverters,   "unit": "EA"},
        {"description": f"Rail Sticks ({rail_length_ft}ft, {rail_system})",
         "part_number": pn["rail"],         "qty": total_rail_sticks, "unit": "EA"},
        {"description": "Splice Kits",
         "part_number": pn["splice"],       "qty": total_splices,     "unit": "EA"},
        {"description": f"Mounting Feet ({roof_attachment}) [{foot_source}]",
         "part_number": foot_pn,            "qty": total_feet,        "unit": "EA"},
        {"description": "T-Bolts / Clicker Bolts (1 per foot)",
         "part_number": pn["t_bolt"],       "qty": total_feet,        "unit": "EA"},
        {"description": "Stainless Hex Screws (4 per foot)",
         "part_number": pn["screw"],        "qty": total_feet * 4,    "unit": "EA"},
        {"description": "Mid Clamps [2 per inter-panel gap × 2 rails]",
         "part_number": pn["mid"],          "qty": total_mid_clamps,  "unit": "EA"},
        {"description": "End Clamps [4 per row: 2 per rail-end]",
         "part_number": pn["end"],          "qty": total_end_clamps,  "unit": "EA"},
        {"description": "Wire Management Clips (1 per 2 panels)",
         "part_number": pn["wire_clip"],    "qty": total_wire_clips,  "unit": "EA"},
        {"description": "Ground Lugs (1 per rail)",
         "part_number": pn["ground_lug"],   "qty": total_ground_lugs, "unit": "EA"},
    ]
    bom += cable_bom
    bom = [item for item in bom if item["qty"] > 0]

    summary = (
        f"{num_rows} row(s) x {panels_per_row} panels ({panel_orientation}). "
        f"Rail run: {round(rail_run_in,1)}in per row. "
        f"{sticks_per_row_rail} × {rail_length_ft}ft stick(s) per rail"
        f"{' + splice' if splices_per_row_rail else ''}. "
        f"Feet: {total_feet} ({foot_source}). "
        f"Mid clamps: {total_mid_clamps}  End clamps: {total_end_clamps}. "
        f"Inverter system: {inverter_system}."
    )
    return json.dumps({"summary": summary, "bom": bom}, indent=2)
'''

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  UPDATED bom_calculator SYSTEM MESSAGE                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
NEW_BOM_SYS = """You are a solar installation BOM calculator. Follow these steps IN ORDER:

STEP 1 — Call lookup_similar_jobs first.
  Use panel_count, panel_orientation, and roof_attachment from the PDF Extractor.

STEP 2 — Call calculate_solar_bom with these arguments:
  PDF Extractor field            → tool argument
  panel_count                   → panel_count
  panel_orientation             → panel_orientation  ("portrait" or "landscape")
  panels_per_row                → panels_per_row
  panel_model width             → panel_width_in     (default 40.9)
  panel_model height            → panel_height_in    (default 67.9)
  inverter_count                → inverter_count     (0 = auto 1-per-panel)
  inverter_system_type          → inverter_system    ← CRITICAL (see below)
  mounting_system               → rail_system        (e.g. "IronRidge QM ClickFit")
  rail_length_ft                → rail_length_ft     (default 14, confirm from drawings)
  roof_type                     → roof_attachment    (comp_shingle/tile/metal_standing_seam/flat)
  mounting_foot_count           → mounting_foot_count (0 = formula; use vision blue-dot count if given)

  ── INVERTER SYSTEM SELECTION (inverter_system arg) ──────────────────────────
  PDF says Q.CELLS Q.MI / "integrated microinverter" / "AC module"
    → inverter_system = "qcells_integrated"

  PDF says Enphase IQ (any model) / Enphase Q-Cable visible
    → inverter_system = "enphase_iq"

  PDF says Hoymiles / HMS / HMT
    → inverter_system = "hoymiles"

  PDF says SolarEdge with P-series optimizers
    → inverter_system = "solaredge"

  PDF says central/string inverter only (Fronius, SMA, Growatt, Solis, etc.), no optimizers
    → inverter_system = "string"

  PDF says string inverter WITH a separate combiner / home-run DC cables
    → inverter_system = "string_central"

  ── CLAMP RULE (already in tool, shown here for your cross-check) ─────────────
  Mid clamps = 2 × (panels_per_row − 1) × num_rows
  End clamps = 4 × num_rows
  Example: 6 rows × 4 panels → mids = 2×3×6 = 36 ; ends = 4×6 = 24

STEP 3 — Cross-check vs verified examples from Step 1.
  If any line item differs by > 20% and you cannot explain why, flag for human review.

STEP 4 — Output:
  a) Summary line from the tool
  b) Full BOM table: qty × description [part_number]
  c) Electrical equipment from the PDF (listed separately, NOT in the tool call):
     main panel size, PV breaker, disconnect, fuse, subpanel upgrade
  d) Any flagged discrepancies

Do NOT say TERMINATE — the Excel Writer goes next.

--- WORKED EXAMPLE A (landscape, QM ClickFit, Q.CELLS integrated) ---
PDF: 24 panels landscape, 4/row, QM ClickFit, comp shingle, Q.MI microinverter, 58 mounting feet

calculate_solar_bom(
  panel_count=24, panel_orientation="landscape", panels_per_row=4,
  panel_height_in=67.9, inverter_count=24,
  inverter_system="qcells_integrated",
  rail_system="IronRidge QM ClickFit", rail_length_ft=14,
  roof_attachment="comp_shingle", mounting_foot_count=58)

Expected clamp check: mids=2×3×6=36, ends=4×6=24 ✓

--- WORKED EXAMPLE B (portrait, XR100, Enphase) ---
PDF: 20 panels portrait, 5/row, IronRidge XR100, tile, Enphase IQ8

calculate_solar_bom(
  panel_count=20, panel_orientation="portrait", panels_per_row=5,
  panel_width_in=40.9, inverter_count=20,
  inverter_system="enphase_iq",
  rail_system="IronRidge XR100", rail_length_ft=14,
  roof_attachment="tile", mounting_foot_count=0)
"""

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  UPDATED vision prompt (extract_pdf_data) — add blue-dot + inverter type   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
# We patch just the vision instruction text inside the existing tool source
# by replacing the prompt string section.
OLD_VISION_PROMPT_SNIP = '"QUANTITIES & LAYOUT:\\n"'
NEW_VISION_TEXT = '''(
                        "You are analyzing a solar installation engineering / permit sheet PDF. "
                        "The raw extracted text is provided below, followed by images of every page.\\n\\n"
                        "Analyze BOTH the text AND every page image carefully. Extract the following, "
                        "giving priority to what you can visually see in diagrams when it "
                        "conflicts with the text:\\n\\n"
                        "QUANTITIES & LAYOUT:\\n"
                        "- Total panel count: COUNT individual panel rectangles in the roof layout "
                        "  diagram — do NOT rely solely on the number written in text. "
                        "  Report 'diagram count = X, text says Y' if they differ.\\n"
                        "- Panel rows and columns (e.g. 6 rows × 4 columns per row)\\n"
                        "- Panel orientation per row (portrait or landscape)\\n"
                        "- Which roof facets / sections have panels\\n\\n"
                        "MOUNTING FEET (CRITICAL — count carefully):\\n"
                        "- Count every blue dot, filled circle, or marked attachment point "
                        "  on the roof layout diagram. Each dot = 1 mounting foot. "
                        "  Report the exact total: 'Mounting feet (blue dots) = X'.\\n"
                        "- Note the foot spacing pattern if visible (e.g. 12in from ends, 48in between).\\n\\n"
                        "CLAMP VERIFICATION:\\n"
                        "- Between each adjacent pair of panels in a row there are 2 mid clamps "
                        "  (one on the top rail, one on the bottom rail). "
                        "  Confirm or flag if the engineering shows a different arrangement.\\n"
                        "- At each row end (left + right): 2 end clamps (one per rail). "
                        "  Report if the drawings show a different number.\\n\\n"
                        "EQUIPMENT (read model labels in diagrams AND text):\\n"
                        "- Panel model number and individual watt rating\\n"
                        "- Inverter brand, model, and TYPE — classify as one of:\\n"
                        "    * qcells_integrated  (Q.CELLS Q.MI / all-in-one AC module)\\n"
                        "    * enphase_iq         (Enphase IQ8, IQ7, IQ6, Q-Cable visible)\\n"
                        "    * hoymiles           (Hoymiles HMS/HMT microinverter)\\n"
                        "    * solaredge          (SolarEdge inverter + P-series optimizers)\\n"
                        "    * string             (Fronius, SMA, Growatt, Solis, etc. — no optimizers)\\n"
                        "    * string_central     (string inverter with DC combiner / home-run cables)\\n"
                        "  State the classification explicitly: 'inverter_system = qcells_integrated'\\n"
                        "- Racking / mounting system brand and product line\\n"
                        "- Roof type (comp shingle, tile, metal, flat/TPO)\\n"
                        "- Rail stick length if shown on drawings (default assume 14ft)\\n\\n"
                        "ELECTRICAL (read single-line diagram AND schedules):\\n"
                        "- Main service panel size (amps)\\n"
                        "- Main breaker size\\n"
                        "- PV breaker size\\n"
                        "- AC disconnect type and fuse/breaker size\\n"
                        "- Is a new subpanel or main panel upgrade being installed? (Yes/No)\\n"
                        "- Wire gauge and conduit type if shown\\n\\n"
                        "OTHER:\\n"
                        "- Fire setback annotations\\n"
                        "- System total DC watts and AC output\\n"
                        "- Any special conditions or design notes\\n\\n"
                        "FORMAT YOUR RESPONSE with clear section headers matching the categories above. "
                        "State 'mounting_foot_count = X' and 'inverter_system = <type>' explicitly "
                        "so the BOM Calculator can parse them directly.\\n\\n"
                        f"EXTRACTED TEXT:\\n{text_content}"
                    )'''

# Validate BOM source compiles
try:
    compile(NEW_BOM_CALC_SOURCE, "<string>", "exec")
    print("calculate_solar_bom source compiles OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR in BOM calc: {e}")
    conn.close()
    exit(1)

# ── Patch the team ────────────────────────────────────────────────────────────
bom_updated = False
pdf_updated  = False

for p in team["config"]["participants"]:
    name = p["config"]["name"]

    if name == "bom_calculator":
        # Update system message
        p["config"]["system_message"] = NEW_BOM_SYS
        print("Updated bom_calculator system_message")

        # Update calculate_solar_bom tool source
        for t in p["config"]["workbench"]["config"]["tools"]:
            if t["config"]["name"] == "calculate_solar_bom":
                t["config"]["source_code"] = NEW_BOM_CALC_SOURCE
                t["description"] = (
                    "Calculate solar BOM with corrected clamp math (2 mids per gap × 2 rails, "
                    "4 ends per row), 14ft default rail sticks, vision-derived mounting foot count, "
                    "and manufacturer-specific cable/connector system "
                    "(qcells_integrated / enphase_iq / hoymiles / solaredge / string)."
                )
                print("Updated calculate_solar_bom tool")
                bom_updated = True

    if name == "pdf_extractor":
        # Patch the vision content block inside the existing tool source
        for t in p["config"]["workbench"]["config"]["tools"]:
            if t["config"]["name"] == "extract_pdf_data":
                src = t["config"]["source_code"]
                # Replace from the opening ( of the content list text block
                OLD_MARKER = '                    "You are analyzing a solar installation engineering / permit sheet PDF. "'
                NEW_MARKER_START = '                    ('
                if OLD_MARKER in src:
                    # Find the full old text block (from OLD_MARKER to the closing ,)
                    start = src.index(OLD_MARKER)
                    # Walk to end of the string block (find the matching closing ) + ,)
                    # Simpler: replace from OLD_MARKER to the f"EXTRACTED TEXT line
                    end_marker = '                        f"EXTRACTED TEXT:\\n{text_content}"\n                    )\n'
                    end_idx = src.index('f"EXTRACTED TEXT:\\n{text_content}"')
                    # Include the closing line
                    closing = '\n                    )\n'
                    end_full = end_idx + len('f"EXTRACTED TEXT:\\n{text_content}"') + len(closing)
                    new_src = src[:start] + NEW_VISION_TEXT.lstrip() + src[end_full:]
                    t["config"]["source_code"] = new_src
                    print("Updated extract_pdf_data vision prompt")
                    pdf_updated = True
                else:
                    print("WARNING: Could not locate old vision prompt marker — skipping pdf_extractor patch")
                    print("  (run upgrade_pdf_vision.py first if you haven't)")

if not bom_updated:
    print("WARNING: calculate_solar_bom not updated — check participant names")

c.execute("UPDATE team SET component = ? WHERE id = ?", (json.dumps(team), team_id))
conn.commit()
print(f"\nSaved to database (team id={team_id}).")
conn.close()

if not pdf_updated:
    print("\nNOTE: The vision prompt patch was skipped.")
    print("The BOM calculator improvements (clamps, rails, connectors) are still applied.")
    print("To also update the vision prompt, re-run upgrade_pdf_vision.py then re-run this script.")
