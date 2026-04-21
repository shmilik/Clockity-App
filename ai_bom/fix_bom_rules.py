"""
Applies the following corrections to the Solar BOM Team's calculate_solar_bom tool:

CORRECTED RULES (from field feedback on Jeffrey Hanson job):
  Screws:        3 per foot (was 4)
  Ground lugs:   1 per row (was 1 per rail = 2 per row)
  Wire management: 1 pack of 10" zip ties (flat qty, was per-panel clips)
  Conduit/wire:  NOT included in BOM output
  Rail sticks:   Add override_sticks / override_splices params so agent can pass
                 exact counts from engineering drawings or vision
  Zip ties:      1 pack regardless of job size

ELECTRICAL LOGIC (fused disconnect):
  If has_fused_disconnect = True:
    - NO PV interconnect breaker
    - Add: 1 × 15A/2P breaker (inside Q.HOME combiner box, 1 per job)
    - Add: 1 × 20A Eaton BR 2-pole breaker per string (supply-side of combiner)
  If has_fused_disconnect = False:
    - Standard: add PV breaker (size caller supplies via pv_breaker_size arg)

MULTI-ROOF / RAIL ACCURACY:
  Added override_sticks and override_splices — when the vision reads the engineering
  schedule and finds "XR-10-168M: 21 pieces" or the user specifies, these override
  the formula so the agent never has to guess on complex multi-roof jobs.
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
NEW_CALC_SRC = r'''
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
    num_strings: int = 0,
    override_sticks: int = 0,
    override_splices: int = 0,
    has_fused_disconnect: bool = False,
    pv_breaker_size: int = 0,
) -> str:
    """Calculate a detailed solar installation Bill of Materials with part numbers.

    CLAMP RULES:
      Mid clamps = 2 × (panels_per_row - 1) × num_rows
        (2 mid clamps per inter-panel gap: 1 top rail + 1 bottom rail)
      End clamps = 4 × num_rows
        (2 per row-end × 2 ends per row)

    MOUNTING FEET:
      If mounting_foot_count > 0, uses that (vision blue-dot count).
      Otherwise uses foot-spacing formula.

    RAIL STICKS / SPLICES:
      If override_sticks > 0, uses that directly (from engineering schedule or user).
      Otherwise computes from rail_run and rail_length_ft.
      For multi-roof jobs or complex layouts, always prefer override_sticks.

    SCREWS:  3 per foot (NOT 4)
    GROUND LUGS: 1 per row (NOT 1 per rail)
    WIRE MANAGEMENT: 1 pack of 10-inch zip ties (flat, NOT per panel)

    ELECTRICAL (has_fused_disconnect):
      True  → no PV interconnect breaker; add 15A/2P combiner breaker (1 per job)
               + 20A Eaton BR 2-pole breaker per string (num_strings or 1 if unset)
      False → add PV breaker at pv_breaker_size amps if provided

    CONNECTOR / CABLE (inverter_system):
      qcells_integrated  Q.CELLS AC daisy-chain + terminator caps + combiner leads
      enphase_iq         Enphase Q-Cable trunk + tap connectors + terminator caps
      hoymiles           MC4 pairs + Hoymiles AC bus cable
      solaredge          MC4 pairs + optimizer DC leads
      string             MC4 connector pairs (1 per inter-panel DC connection)
      string_central     MC4 pairs + DC home-run cable per string

    Args:
        panel_count:          Total solar panels
        panel_orientation:    "portrait" or "landscape"
        panels_per_row:       Panels in one horizontal row
        panel_width_in:       Short-side width in inches (default 40.9)
        panel_height_in:      Long-side height in inches (default 67.9)
        inverter_count:       Microinverter count override (0 = 1 per panel)
        inverter_system:      See CONNECTOR / CABLE above
        rail_system:          Rail brand (IronRidge XR10, IronRidge XR100, IronRidge QM ClickFit, Unirac SolarMount)
        rail_length_ft:       Stock rail stick length in feet (default 14)
        roof_attachment:      comp_shingle | tile | metal_standing_seam | flat
        mounting_foot_count:  Blue-dot count from vision (0 = use formula)
        num_strings:          Number of branch circuit strings (used for electrical calc)
        override_sticks:      Exact rail stick count from engineering schedule (0 = formula)
        override_splices:     Exact splice kit count from engineering schedule (0 = formula)
        has_fused_disconnect: True = fused AC disconnect present (changes electrical BOM)
        pv_breaker_size:      PV breaker amps (used only if has_fused_disconnect=False)

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
    strings     = num_strings if num_strings > 0 else max(num_rows, 1)

    # ── Rail geometry ─────────────────────────────────────────────────────────
    if is_portrait:
        rail_run_in = panels_per_row * panel_width_in
    else:
        rail_run_in = panels_per_row * panel_height_in

    rail_stick_in = rail_length_ft * 12.0

    if override_sticks > 0:
        total_rail_sticks = override_sticks
        total_splices     = override_splices if override_splices > 0 else max(override_sticks - 2 * num_rows, 0)
        sticks_note       = "from engineering schedule"
    else:
        sticks_per_row_rail  = math.ceil(rail_run_in / rail_stick_in)
        splices_per_row_rail = max(sticks_per_row_rail - 1, 0)
        total_rail_sticks    = sticks_per_row_rail * 2 * num_rows
        total_splices        = splices_per_row_rail * 2 * num_rows
        sticks_note          = "formula"

    # ── Clamps (field-verified rules) ─────────────────────────────────────────
    total_mid_clamps = 2 * max(panels_per_row - 1, 0) * num_rows
    total_end_clamps = 4 * num_rows

    # ── Mounting feet ─────────────────────────────────────────────────────────
    if mounting_foot_count > 0:
        total_feet = mounting_foot_count
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
        feet_per_rail = count_feet_for_rail(rail_run_in)
        total_feet    = feet_per_rail * 2 * num_rows
        foot_source   = "formula"

    # ── Inverters ─────────────────────────────────────────────────────────────
    total_inverters = inverter_count if inverter_count > 0 else panel_count

    # ── Part numbers ──────────────────────────────────────────────────────────
    PARTS = {
        "xr10":        {"rail": "XR-10-168M",     "splice": "XR-10-SP",     "mid": "CLM-0003B", "end": "CLM-0002B", "wire_clip": "", "ground_lug": "GR-LUG-100", "t_bolt": "HS-T-BLT-0100", "screw": "HS-M8-SS"},
        "xr100":       {"rail": "XR-100-204B",    "splice": "XR-100-SP",    "mid": "CLM-0003B", "end": "CLM-0002B", "wire_clip": "", "ground_lug": "GR-LUG-100", "t_bolt": "HS-T-BLT-0100", "screw": "HS-M8-SS"},
        "qmclickfit":  {"rail": "QM-CF-SD-168M",  "splice": "QM-CF-SPLICE", "mid": "QM-MIDCLAMP","end": "QM-ENDCLAMP","wire_clip": "","ground_lug": "QM-GR-LUG",  "t_bolt": "QM-CLICKER-BOLT","screw": "QM-SS-SCREW"},
        "unirac":      {"rail": "SM-RL-168",       "splice": "SM-SPLICE",    "mid": "SM-MC",      "end": "SM-EC",     "wire_clip": "", "ground_lug": "SM-GL",       "t_bolt": "SM-TBOLT",       "screw": "SM-SCREW"},
    }
    FOOT_PARTS = {
        "comp_shingle":        "FW-LFAB-200B",
        "tile":                "FW-LFAB-TILE",
        "metal_standing_seam": "FW-LFAB-MS",
        "flat":                "FW-LFAB-FLAT",
    }

    def pick_parts(rail_sys):
        rs = rail_sys.lower().replace(" ", "").replace("-", "").replace("_", "")
        if "xr10" in rs and "xr100" not in rs:        return PARTS["xr10"]
        if "xr100" in rs:                              return PARTS["xr100"]
        if "clickfit" in rs or "qmcf" in rs:           return PARTS["qmclickfit"]
        if "unirac" in rs or "solarmount" in rs:       return PARTS["unirac"]
        return PARTS["xr100"]  # default

    pn       = pick_parts(rail_system)
    foot_pn  = FOOT_PARTS.get(roof_attachment, "FW-LFAB-200B")
    total_ground_lugs = num_rows    # 1 per row (not per rail)

    # ── Connector / cable system ──────────────────────────────────────────────
    inv_sys    = inverter_system.lower().strip()
    cable_bom  = []

    if inv_sys == "qcells_integrated":
        cable_bom = [
            {"description": "Q.CELLS AC Daisy-Chain Cable (module-to-module, 1 per inter-module gap)",
             "part_number": "QCELLS-ACCABLE", "qty": total_inverters - num_rows, "unit": "EA"},
            {"description": "Q.CELLS Branch Circuit End Cap / Terminator",
             "part_number": "QCELLS-TERMCAP", "qty": num_rows * 2,              "unit": "EA"},
            {"description": "Q.CELLS Combiner Branch Leads (1 per string/row)",
             "part_number": "QCELLS-LEAD",    "qty": num_rows,                  "unit": "EA"},
        ]
    elif inv_sys == "enphase_iq":
        cable_bom = [
            {"description": "Enphase Q-Cable Trunk Cable (240V, 1 per branch circuit)",
             "part_number": "Q-12-240-L-240",  "qty": strings,            "unit": "EA"},
            {"description": "Enphase Q-Cable Tap Connector (1 per microinverter)",
             "part_number": "Q-CONN-TAP",       "qty": total_inverters,   "unit": "EA"},
            {"description": "Enphase Q-Cable Terminator Cap (1 per branch end)",
             "part_number": "Q-CAP-240",        "qty": strings,           "unit": "EA"},
        ]
    elif inv_sys == "solaredge":
        gaps = max(panels_per_row - 1, 0) * num_rows
        cable_bom = [
            {"description": "SolarEdge Optimizer DC Lead Extension (MC4)",
             "part_number": "SE-OPTLEAD-MC4", "qty": total_inverters, "unit": "EA"},
            {"description": "MC4 Connector Pairs (inter-optimizer DC string)",
             "part_number": "MC4-PAIR",        "qty": gaps,            "unit": "PAIR"},
        ]
    elif inv_sys == "hoymiles":
        gaps = max(panels_per_row - 1, 0) * num_rows
        cable_bom = [
            {"description": "MC4 Connector Pairs (Hoymiles DC string)",
             "part_number": "MC4-PAIR",  "qty": gaps + num_rows,  "unit": "PAIR"},
            {"description": "Hoymiles AC Bus Cable (1 per string)",
             "part_number": "HM-ACBUS",  "qty": strings,          "unit": "EA"},
        ]
    elif inv_sys in ("string", "string_central"):
        gaps = max(panels_per_row - 1, 0) * num_rows
        cable_bom = [
            {"description": "MC4 Connector Pairs (1 per panel-to-panel DC connection)",
             "part_number": "MC4-PAIR", "qty": gaps, "unit": "PAIR"},
        ]
        if inv_sys == "string_central":
            cable_bom.append({
                "description": "DC Home-Run Cable (panel string to combiner, per string)",
                "part_number": "DC-HOMERUN-10AWG", "qty": strings, "unit": "EA"})

    # ── Electrical BOM ────────────────────────────────────────────────────────
    electrical_bom = []
    if has_fused_disconnect:
        # Fused disconnect present → no PV interconnect breaker
        # 15A/2P breaker inside the combiner box (1 per job)
        # 20A Eaton BR 2-pole breaker per string (supply-side of combiner)
        electrical_bom = [
            {"description": "15A/2P Breaker (inside combiner box, 1 per job)",
             "part_number": "BR115",   "qty": 1,       "unit": "EA"},
            {"description": "20A Eaton BR 2-Pole Breaker (1 per string, supply-side of combiner)",
             "part_number": "BR220",   "qty": strings,  "unit": "EA"},
        ]
    else:
        if pv_breaker_size > 0:
            electrical_bom = [
                {"description": f"{pv_breaker_size}A/2P PV Interconnect Breaker",
                 "part_number": f"BR{pv_breaker_size}",  "qty": 1,  "unit": "EA"},
            ]

    # ── Assemble BOM ──────────────────────────────────────────────────────────
    bom = [
        {"description": "Solar Panels",
         "part_number": "SEE-ENGINEERING",  "qty": panel_count,       "unit": "EA"},
        {"description": f"Inverters ({inverter_system})",
         "part_number": "SEE-ENGINEERING",  "qty": total_inverters,   "unit": "EA"},
        {"description": f"Rail Sticks ({rail_length_ft}ft, {rail_system}) [{sticks_note}]",
         "part_number": pn["rail"],          "qty": total_rail_sticks, "unit": "EA"},
        {"description": "Splice Kits",
         "part_number": pn["splice"],        "qty": total_splices,     "unit": "EA"},
        {"description": f"Mounting Feet ({roof_attachment}) [{foot_source}]",
         "part_number": foot_pn,             "qty": total_feet,        "unit": "EA"},
        {"description": "T-Bolts / Clicker Bolts (1 per foot)",
         "part_number": pn["t_bolt"],        "qty": total_feet,        "unit": "EA"},
        {"description": "Stainless Hex Screws (3 per foot)",
         "part_number": pn["screw"],         "qty": total_feet * 3,    "unit": "EA"},
        {"description": "Mid Clamps [2 per inter-panel gap × 2 rails]",
         "part_number": pn["mid"],           "qty": total_mid_clamps,  "unit": "EA"},
        {"description": "End Clamps [4 per row: 2 per rail-end]",
         "part_number": pn["end"],           "qty": total_end_clamps,  "unit": "EA"},
        {"description": "10-Inch Zip Ties (1 pack)",
         "part_number": "ZIPTIE-10IN-PK",   "qty": 1,                 "unit": "PACK"},
        {"description": "Ground Lugs (1 per row)",
         "part_number": pn["ground_lug"],    "qty": total_ground_lugs, "unit": "EA"},
    ]
    bom += cable_bom
    bom += electrical_bom
    bom = [item for item in bom if item["qty"] > 0]

    summary = (
        f"{num_rows} row(s) x {panels_per_row} panels ({panel_orientation}). "
        f"Rail: {total_rail_sticks} x {rail_length_ft}ft sticks [{sticks_note}], "
        f"{total_splices} splices. "
        f"Feet: {total_feet} ({foot_source}). "
        f"Mids: {total_mid_clamps}  Ends: {total_end_clamps}. "
        f"Screws: {total_feet * 3} (3/foot). "
        f"Ground lugs: {total_ground_lugs} (1/row). "
        f"Inverter system: {inverter_system}. "
        f"Electrical: {'fused disconnect (15A combiner + ' + str(strings) + 'x 20A Eaton BR)' if has_fused_disconnect else 'standard'}."
    )
    return json.dumps({"summary": summary, "bom": bom}, indent=2)
'''

# ── Updated bom_calculator system message ─────────────────────────────────────
NEW_BOM_SYS = """You are a solar installation BOM calculator. Follow these steps IN ORDER:

STEP 1 — Call lookup_similar_jobs first.

STEP 2 — Call calculate_solar_bom with these mapped arguments:
  PDF field                      → tool argument
  panel_count                   → panel_count
  panel_orientation             → panel_orientation
  panels_per_row                → panels_per_row
  panel width (short side)      → panel_width_in  (default 40.9; portrait horizontal)
  panel height (long side)      → panel_height_in (default 67.9; landscape horizontal)
  inverter_count                → inverter_count  (0 = 1 per panel)
  inverter_system_type          → inverter_system  ← CRITICAL (see below)
  mounting_system               → rail_system
  rail_length_ft (default 14)   → rail_length_ft
  roof_type                     → roof_attachment
  mounting_foot_count (blue dots) → mounting_foot_count (0 = formula)
  num_strings (branch circuits) → num_strings  ← use when PDF explicitly states strings
  override_sticks               → override_sticks  ← use when PDF/schedule states exact rail count
  override_splices              → override_splices  ← use when PDF/schedule states exact splice count
  has_fused_disconnect          → has_fused_disconnect (True/False)
  pv_breaker_size               → pv_breaker_size (amps, only when no fused disconnect)

  ── INVERTER SYSTEM SELECTION ─────────────────────────────────────────────────
  Q.CELLS Q.MI / "integrated microinverter" / "AC module"  → "qcells_integrated"
  Enphase IQ (any model) / Q-Cable visible                 → "enphase_iq"
  Hoymiles HMS/HMT                                         → "hoymiles"
  SolarEdge + P-series optimizers                          → "solaredge"
  String inverter only (Fronius, SMA, Growatt, Solis)      → "string"
  String inverter + DC combiner / home-run cables          → "string_central"

  ── RAIL SYSTEM SELECTION ────────────────────────────────────────────────────
  "IronRidge XR10"           → for XR-10 rail (14ft sticks, XR-10-168M)
  "IronRidge XR100"          → for XR-100 rail (longer, larger profile)
  "IronRidge QM ClickFit"    → for QM-CF ClickFit system
  "Unirac SolarMount"        → for Unirac SM rail

  ── MULTI-ROOF / OVERRIDE RULES ──────────────────────────────────────────────
  When the PDF has panels on 2+ roofs or mixed portrait/landscape arrays, the
  formula rail count will be inaccurate. In those cases:
    1. Look for a material schedule or "rail sticks: X" in the vision output
    2. Set override_sticks and override_splices to those values
    3. If not stated, sum each roof's sticks separately and add them together
  When override_sticks is provided, always also set override_splices explicitly.

  ── ELECTRICAL RULES ─────────────────────────────────────────────────────────
  If there is a FUSED AC disconnect (e.g. 60A fused, 2 fuse holders):
    → has_fused_disconnect = True
    → pv_breaker_size = 0
    → The tool will add: 1×15A combiner breaker + 1×20A Eaton BR per string
    → DO NOT add any PV interconnect breaker or conduit/wire to BOM

  If there is only an AC breaker disconnect (NOT fused):
    → has_fused_disconnect = False
    → pv_breaker_size = (the PV breaker size from single-line diagram)

  ── WHAT NOT TO INCLUDE ──────────────────────────────────────────────────────
  Do NOT add conduit, wire, or wire runs to the BOM output.

STEP 3 — Cross-check vs similar verified examples from Step 1.
  Flag any line item > 20% different from a comparable verified job.

STEP 4 — Output:
  a) Summary line from the tool
  b) Full BOM table: qty × description [part_number]
  c) Electrical equipment (from tool output — already included when has_fused_disconnect=True):
     - If fused disconnect: note the 15A combiner breaker and 20A Eaton BR per string
     - Main panel size, disconnect type, subpanel upgrade (narrative only, not in BOM table)
  d) Any flagged discrepancies

Do NOT say TERMINATE — the Excel Writer goes next.

--- WORKED EXAMPLE A: Jeffrey Hanson / 7266 14th St N (multi-roof, XR10, Q.CELLS integrated) ---
  PDF: 27 panels portrait, 3 strings of 9, XR10, comp shingle, Q.MI, fused 60A disconnect
  Vision shows: mounting_foot_count=90, override_sticks=21, override_splices=10

  calculate_solar_bom(
    panel_count=27, panel_orientation="portrait", panels_per_row=9,
    panel_width_in=44.6, panel_height_in=67.8,
    inverter_count=27, inverter_system="qcells_integrated",
    rail_system="IronRidge XR10", rail_length_ft=14,
    roof_attachment="comp_shingle",
    mounting_foot_count=90, num_strings=3,
    override_sticks=21, override_splices=10,
    has_fused_disconnect=True)

  Expected: 21 sticks, 10 splices, 90 feet, 90 T-bolts, 270 screws,
            mid=2×8×3=48, end=4×3=12 (for 3 rows of 9),
            1×15A combiner breaker, 3×20A Eaton BR ✓

--- WORKED EXAMPLE B: Hays St (QM ClickFit, Q.CELLS integrated, fused) ---
  calculate_solar_bom(
    panel_count=24, panel_orientation="landscape", panels_per_row=4,
    panel_height_in=67.9, inverter_count=24,
    inverter_system="qcells_integrated",
    rail_system="IronRidge QM ClickFit", rail_length_ft=14,
    roof_attachment="comp_shingle",
    mounting_foot_count=58, num_strings=3,
    override_sticks=0, override_splices=0,
    has_fused_disconnect=True)

--- WORKED EXAMPLE C: Standard Enphase, single roof ---
  calculate_solar_bom(
    panel_count=20, panel_orientation="portrait", panels_per_row=5,
    panel_width_in=40.9, inverter_count=20,
    inverter_system="enphase_iq",
    rail_system="IronRidge XR100", rail_length_ft=14,
    roof_attachment="tile",
    mounting_foot_count=0, num_strings=2,
    has_fused_disconnect=False, pv_breaker_size=30)
"""

# ── Updated vision prompt extraction request ──────────────────────────────────
VISION_EXTRA_INSTRUCTIONS = (
    "RAIL SCHEDULE (look carefully on every page for a material or equipment schedule):\n"
    "- Find any table listing XR-10-168M, XR-100-204B, QM-CF-SD-168M, or similar rail part numbers.\n"
    "- If you find a quantity next to the rail part number, report it as: override_sticks = X\n"
    "- If you see a splice kit quantity, report it as: override_splices = X\n"
    "- If no schedule is found, note: override_sticks = not found (use formula)\n\n"
    "MOUNTING FEET (CRITICAL - count carefully):\n"
    "- Count every blue dot, filled circle, or marked attachment point on the roof layout diagram.\n"
    "  Each dot = 1 mounting foot. Report: mounting_foot_count = X\n\n"
    "STRINGS / BRANCH CIRCUITS:\n"
    "- Count the number of branch circuits or strings (e.g. String 1: 9 units).\n"
    "- Report: num_strings = X\n\n"
    "DISCONNECT TYPE:\n"
    "- If the disconnect has fuses (e.g. 60A fused, 2x50A fuses): has_fused_disconnect = True\n"
    "- If it is a breaker-only disconnect: has_fused_disconnect = False\n"
    "- If fused: do NOT report a PV interconnect breaker. Report: 15A/2P breaker in combiner and 20A Eaton BR x num_strings.\n"
    "- If breaker-only: report: pv_breaker_size = X amps\n\n"
    "DO NOT include conduit or wire in the extracted data.\n\n"
)

# ── Compile check ─────────────────────────────────────────────────────────────
try:
    compile(NEW_CALC_SRC, "<string>", "exec")
    print("calculate_solar_bom compiles OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    conn.close()
    exit(1)

# ── Patch the team ─────────────────────────────────────────────────────────────
bom_updated = sys_updated = vision_updated = False

for p in team["config"]["participants"]:
    name = p["config"]["name"]

    if name == "bom_calculator":
        p["config"]["system_message"] = NEW_BOM_SYS
        sys_updated = True
        print("Updated bom_calculator system_message")
        for t in p["config"]["workbench"]["config"]["tools"]:
            if t["config"]["name"] == "calculate_solar_bom":
                t["config"]["source_code"] = NEW_CALC_SRC
                t["description"] = (
                    "Calculate solar BOM: 3 screws/foot, 1 ground lug/row, 1 pack zip ties, "
                    "fused-disconnect electric logic (15A combiner + 20A Eaton BR/string), "
                    "multi-roof override_sticks/override_splices support, manufacturer connectors."
                )
                bom_updated = True
                print("Updated calculate_solar_bom tool")

    if name == "pdf_extractor":
        for t in p["config"]["workbench"]["config"]["tools"]:
            if t["config"]["name"] == "extract_pdf_data":
                src = t["config"]["source_code"]
                # Inject rail/disconnect/foot/string extraction after the main prompt block
                # Find the format instruction line and prepend our additions before it
                TARGET = "FORMAT YOUR RESPONSE with clear section headers"
                if TARGET in src:
                    replacement = (
                        "RAIL SCHEDULE (look on every page for a material or equipment schedule):\\n"
                        "- Find any table listing XR-10-168M, XR-100-204B, QM-CF-SD-168M, or similar.\\n"
                        "- Report rail stick quantity as: override_sticks = X\\n"
                        "- Report splice kit quantity as: override_splices = X\\n"
                        "- If not found: override_sticks = not found (use formula)\\n\\n"
                        "MOUNTING FEET (CRITICAL - count carefully):\\n"
                        "- Count every blue dot or circle on the roof layout. Each = 1 mounting foot.\\n"
                        "- Report: mounting_foot_count = X\\n\\n"
                        "STRINGS: Count branch circuits. Report: num_strings = X\\n\\n"
                        "DISCONNECT: If fuses present (e.g. 60A fused): has_fused_disconnect = True\\n"
                        "  If fused: report 15A combiner breaker + 20A Eaton BR x strings. No PV breaker.\\n"
                        "  If breaker-only: has_fused_disconnect = False, pv_breaker_size = X amps\\n"
                        "DO NOT include conduit or wire.\\n\\n"
                    )
                    src = src.replace(TARGET, replacement + TARGET, 1)
                    try:
                        compile(src, "<string>", "exec")
                        t["config"]["source_code"] = src
                        print("Updated extract_pdf_data vision prompt (compiles OK)")
                        vision_updated = True
                    except SyntaxError as e:
                        print(f"Vision patch syntax error: {e} - skipping pdf_extractor patch")
                        vision_updated = False
                else:
                    print("Could not find vision patch target - skipping pdf_extractor update")

c.execute("UPDATE team SET component = ? WHERE id = ?", (json.dumps(team), team_id))
conn.commit()
print(f"\nSaved to database (team id={team_id}).")
conn.close()

# Quick sanity test
ns = {}
exec(NEW_CALC_SRC, ns)
calc = ns["calculate_solar_bom"]
import json as _json
result = _json.loads(calc(
    panel_count=27, panel_orientation="portrait", panels_per_row=9,
    panel_width_in=44.6, panel_height_in=67.8,
    inverter_count=27, inverter_system="qcells_integrated",
    rail_system="IronRidge XR10", rail_length_ft=14,
    roof_attachment="comp_shingle",
    mounting_foot_count=90, num_strings=3,
    override_sticks=21, override_splices=10,
    has_fused_disconnect=True
))
print("\n=== JEFFREY HANSON TEST ===")
print("SUMMARY:", result["summary"])
print()
print(f"{'QTY':>5}  {'PART':20}  DESCRIPTION")
print("-"*80)
for item in result["bom"]:
    print(f"{item['qty']:>5}  {item['part_number']:20}  {item['description']}")

sticks = next((i["qty"] for i in result["bom"] if "Rail Stick" in i["description"]), None)
splices = next((i["qty"] for i in result["bom"] if "Splice" in i["description"]), None)
feet   = next((i["qty"] for i in result["bom"] if "Mounting Feet" in i["description"]), None)
tbolts = next((i["qty"] for i in result["bom"] if "T-Bolt" in i["description"]), None)
screws = next((i["qty"] for i in result["bom"] if "Screw" in i["description"]), None)
lugs   = next((i["qty"] for i in result["bom"] if "Ground Lug" in i["description"]), None)
zip_   = next((i["qty"] for i in result["bom"] if "Zip" in i["description"]), None)
cbr15  = next((i["qty"] for i in result["bom"] if "15A" in i["description"]), None)
cbr20  = next((i["qty"] for i in result["bom"] if "20A Eaton" in i["description"]), None)

print()
print("CHECKS:")
print(f"  Rail sticks:  {sticks}  (want 21)   {'✓' if sticks==21 else '✗'}")
print(f"  Splice kits:  {splices}  (want 10)   {'✓' if splices==10 else '✗'}")
print(f"  Mount feet:   {feet}  (want 90)   {'✓' if feet==90 else '✗'}")
print(f"  T-bolts:      {tbolts}  (want 90)   {'✓' if tbolts==90 else '✗'}")
print(f"  Screws:       {screws}  (want 270)  {'✓' if screws==270 else '✗'}")
print(f"  Ground lugs:  {lugs}   (want 3)    {'✓' if lugs==3 else '✗'}")
print(f"  Zip ties:     {zip_}   (want 1 pack) {'✓' if zip_==1 else '✗'}")
print(f"  15A combiner: {cbr15}   (want 1)    {'✓' if cbr15==1 else '✗'}")
print(f"  20A Eaton BR: {cbr20}   (want 3)    {'✓' if cbr20==3 else '✗'}")
