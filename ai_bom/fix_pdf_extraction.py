"""
Rewrites extract_pdf_data to use text-first extraction:
  1. pymupdf4llm  -> clean markdown (primary, ~1-3k tokens)
  2. pdfplumber   -> table data (complement)
  3. Vision       -> ONLY if text < 200 chars (scanned/image-only PDF)
                     Uses 100 DPI (not 150) and caps at 8 pages.

Token savings: ~17k-24k per call -> ~1-3k per call for text-based PDFs.
"""

import sqlite3, json

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"

NEW_SOURCE = '''
def extract_pdf_data(pdf_path: str) -> str:
    """Extract all data from a solar engineering PDF using text-first extraction.
    Primary: pymupdf4llm markdown + pdfplumber table extraction (~1-3k tokens).
    Fallback: Vision AI only if text extraction yields < 200 characters (scanned PDF).
    Accepts an absolute Windows file path."""
    import os, sys

    if not os.path.exists(pdf_path):
        return f"ERROR: File not found: {pdf_path}"

    # ── 1. Primary: pymupdf4llm markdown ──────────────────────────────────────
    text_content = ""
    try:
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
        if md and len(md.strip()) > 200:
            text_content = md
    except Exception:
        pass

    # ── 2. Complement: pdfplumber — top-left crop of page 1 + all tables ──────
    top_left_text = ""
    table_content = ""
    try:
        import pdfplumber
        table_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            # Crop top-left quarter of page 1 — this is where panel/inverter info lives
            if pdf.pages:
                p0 = pdf.pages[0]
                w, h = p0.width, p0.height
                # Top-left region: left 55% wide, top 40% tall
                crop = p0.crop((0, 0, w * 0.55, h * 0.40))
                tl = crop.extract_text() or ""
                if tl.strip():
                    top_left_text = tl.strip()

            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables() or []
                for table in tables:
                    rows = []
                    for row in table:
                        if row and any(c for c in row):
                            rows.append(" | ".join(str(c).strip() if c else "" for c in row))
                    if rows:
                        table_pages.append(f"[Table on page {i+1}]\\n" + "\\n".join(rows))
        if table_pages:
            table_content = "\\n\\n".join(table_pages)
    except Exception:
        pass

    # If pymupdf4llm missed text, fall back to pdfplumber plain text
    if not text_content:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    t = page.extract_text() or ""
                    if t.strip():
                        pages.append(f"--- Page {i+1} ---\\n{t}")
            combined = "\\n".join(pages)
            if len(combined.strip()) > 200:
                text_content = combined
        except Exception as e:
            text_content = f"Text extraction error: {e}"

    combined_text = text_content
    if top_left_text:
        combined_text = "=== PAGE 1 TOP-LEFT (project info block — panel model, inverter) ===\\n" + top_left_text + "\\n\\n" + combined_text
    if table_content:
        combined_text += "\\n\\n=== EXTRACTED TABLES ===\\n" + table_content

    # ── 3. Targeted vision: page 4 electrical single-line diagram ─────────────
    # Even in text-based PDFs the SLD is a vector/raster drawing — vision is
    # the only reliable way to read disconnect type, fuse size, and wiring topology.
    import base64
    page4_analysis = ""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        # Use page 4 (index 3); fall back to last page if PDF < 4 pages
        elec_page_idx = min(3, len(doc) - 1)
        page = doc[elec_page_idx]
        mat = fitz.Matrix(110 / 72, 110 / 72)  # 110 DPI — readable but compact
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        page4_b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
        doc.close()

        import anthropic, os, sys
        search_dirs = [
            r"C:\\Users\\info\\OneDrive\\Desktop\\JobTracker",
            r"D:\\ResearchTeam-Portable\\app",
            r"E:\\ResearchTeam-Portable\\app",
        ]
        for d in search_dirs:
            if d and os.path.isdir(d) and d not in sys.path:
                sys.path.insert(0, d)
        api_key = ""
        try:
            import research_config as _cfg
            api_key = _cfg.ANTHROPIC_API_KEY
        except ImportError:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if api_key:
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": (
                        "This is the electrical single-line diagram (SLD) from a solar permit package. "
                        "Analyze it carefully and extract ONLY the following — be concise:\\n\\n"
                        "DISCONNECT:\\n"
                        "- disconnect_type = <AC disconnect | fused disconnect | combined disconnect>\\n"
                        "- disconnect_size = <amperage, e.g. 30A, 60A>\\n"
                        "- disconnect_brand = <brand if visible, e.g. Eaton, Square D, Siemens>\\n"
                        "- disconnect_poles = <SPST / DPST / 2-pole / etc.>\\n\\n"
                        "FUSING (if present):\\n"
                        "- has_fused_disconnect = True or False\\n"
                        "- fuse_size = <amperage per fuse, e.g. 15A, 20A>  (or 'none')\\n"
                        "- fuse_type = <cartridge / blade / other>  (or 'none')\\n\\n"
                        "INTERCONNECTION:\\n"
                        "- interconnection_method = <load side tap | line side tap | supply side | meter socket | utility backfeed>\\n"
                        "- pv_breaker_size = <amperage of the PV breaker in the main panel, e.g. 30A>  (or 'none')\\n"
                        "- main_panel_size = <service amps, e.g. 200A>\\n"
                        "- main_breaker_size = <e.g. 200A>\\n"
                        "- num_strings = <number of DC string circuits shown>\\n\\n"
                        "Use only the labels above. If a field is not shown in the diagram, write 'not shown'."
                    )},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": page4_b64}},
                ]}],
            )
            page4_analysis = resp.content[0].text
    except Exception:
        pass  # silently skip if page 4 vision fails — text analysis still proceeds

    if page4_analysis:
        combined_text += "\\n\\n=== PAGE 4 ELECTRICAL DIAGRAM (vision analysis) ===\\n" + page4_analysis

    # ── 5. Fallback: Vision only for scanned / image-only PDFs ────────────────
    is_scanned = len(combined_text.strip()) < 200

    if is_scanned:
        import base64
        page_images_b64 = []
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            # Cap at 8 pages, 100 DPI (not 150 — cuts image token cost ~45%)
            for page_num in range(min(len(doc), 8)):
                page = doc[page_num]
                mat = fitz.Matrix(100 / 72, 100 / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
                page_images_b64.append(b64)
            doc.close()
        except Exception:
            return "ERROR: Could not extract text or render pages from this PDF."

        try:
            import anthropic
            search_dirs = [
                r"C:\\Users\\info\\OneDrive\\Desktop\\JobTracker",
                r"D:\\ResearchTeam-Portable\\app",
                r"E:\\ResearchTeam-Portable\\app",
            ]
            for d in search_dirs:
                if d and os.path.isdir(d) and d not in sys.path:
                    sys.path.insert(0, d)
            api_key = ""
            try:
                import research_config as _cfg
                api_key = _cfg.ANTHROPIC_API_KEY
            except ImportError:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")

            if not api_key:
                return "ERROR: Scanned PDF detected but no API key found for vision fallback."

            client = anthropic.Anthropic(api_key=api_key)
            content = [{"type": "text", "text": (
                "This is a scanned solar engineering / permit sheet PDF (no selectable text). "
                "Analyze every page image and extract:\\n\\n"
                "- Customer name and address\\n"
                "- Total panel count (count rectangles in roof diagram)\\n"
                "- panel_model = <full model number from the top-left project info block on page 1>\\n"
                "- panel_watts = <watt rating>\\n"
                "- inverter_brand = <brand from top-left block>\\n"
                "- inverter_model = <full model number>\\n"
                "- inverter_system = <enphase_iq | qcells_integrated | hoymiles | solaredge | string | string_central>\\n"
                "- Panel rows, columns, orientation\\n"
                "- mounting_foot_count = X  (count blue dots on roof diagram)\\n"
                "- Racking system and rail stick length\\n"
                "- Roof type\\n"
                "- Main panel size, PV breaker size\\n"
                "- has_fused_disconnect = True/False\\n"
                "- num_strings = X\\n"
                "- override_sticks = X (or \'not found\')\\n"
                "- override_splices = X (or \'not found\')\\n"
                "Use clear section headers. State panel_model, inverter_model, inverter_system, "
                "and mounting_foot_count explicitly."
            )}]
            for i, b64 in enumerate(page_images_b64):
                content.append({"type": "text", "text": f"\\n[Page {i+1}]"})
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                })

            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": content}],
            )
            return "[VISION FALLBACK — scanned PDF]\\n\\n" + resp.content[0].text

        except Exception as vision_err:
            return f"ERROR: Vision fallback failed: {vision_err}"

    # ── 6. Text-based PDF: ask Claude to parse the clean text directly ─────────
    try:
        import anthropic
        search_dirs = [
            r"C:\\Users\\info\\OneDrive\\Desktop\\JobTracker",
            r"D:\\ResearchTeam-Portable\\app",
            r"E:\\ResearchTeam-Portable\\app",
        ]
        for d in search_dirs:
            if d and os.path.isdir(d) and d not in sys.path:
                sys.path.insert(0, d)
        api_key = ""
        try:
            import research_config as _cfg
            api_key = _cfg.ANTHROPIC_API_KEY
        except ImportError:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not api_key:
            return "ERROR: No API key found in research_config or ANTHROPIC_API_KEY."

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "You are parsing a solar installation engineering / permit sheet PDF that has been "
            "converted to text. The section labelled 'PAGE 1 TOP-LEFT' is the project info block "
            "in the top-left corner of the cover sheet — it lists the panel model, inverter model, "
            "and system specs. Prioritize that section for panel and inverter identification.\\n"
            "The section labelled 'PAGE 4 ELECTRICAL DIAGRAM' is a vision analysis of the "
            "single-line diagram — prioritize it for disconnect type, fuse size, and interconnection method.\\n\\n"
            "Extract the following fields and return them as clearly labelled sections:\\n\\n"
            "CUSTOMER:\\n"
            "- Customer name\\n"
            "- Installation address\\n\\n"
            "EQUIPMENT (prioritize PAGE 1 TOP-LEFT block):\\n"
            "- panel_model = <full model number, e.g. Q.CELLS Q.PEAK DUO BLK ML-G10+ 400>\\n"
            "- panel_watts = <watt rating as integer, e.g. 400>\\n"
            "- inverter_brand = <brand name, e.g. Enphase, Hoymiles, SolarEdge, Fronius>\\n"
            "- inverter_model = <full model number, e.g. IQ8A-72-2-US>\\n"
            "- inverter_system = <one of: enphase_iq | qcells_integrated | hoymiles | solaredge | string | string_central>\\n"
            "  Classification guide:\\n"
            "    enphase_iq        — Enphase IQ8/IQ7/IQ6, Q-Cable\\n"
            "    qcells_integrated — Q.CELLS Q.MI / Q.HOME all-in-one AC module\\n"
            "    hoymiles          — Hoymiles HMS/HMT\\n"
            "    solaredge         — SolarEdge + P-series or S-series optimizers\\n"
            "    string            — Fronius, SMA, Growatt, Solis, Sungrow (no optimizers)\\n"
            "    string_central    — string inverter + DC combiner box\\n\\n"
            "SYSTEM:\\n"
            "- Total panel count\\n"
            "- Panel layout: rows, columns, orientation (portrait/landscape)\\n"
            "- Racking brand and product line\\n"
            "- Rail stick length (default 14ft if not stated)\\n"
            "- Roof type (comp shingle / tile / metal / flat)\\n\\n"
            "MOUNTING:\\n"
            "- mounting_foot_count = X  (from engineering schedule or diagram notes)\\n"
            "- num_strings = X  (number of branch circuits / strings)\\n\\n"
            "DISCONNECT (prioritize PAGE 4 ELECTRICAL DIAGRAM section):\\n"
            "- disconnect_type = <AC disconnect | fused disconnect | combined disconnect>\\n"
            "- disconnect_size = <amperage, e.g. 30A, 60A>\\n"
            "- disconnect_brand = <brand if visible>\\n"
            "- has_fused_disconnect = True or False\\n"
            "- fuse_size = <amps per fuse, e.g. 15A>  (or 'none')\\n\\n"
            "INTERCONNECTION (prioritize PAGE 4 ELECTRICAL DIAGRAM section):\\n"
            "- interconnection_method = <load side tap | line side tap | supply side | meter socket>\\n"
            "- pv_breaker_size = <amps>  (or 'none — fused disconnect')\\n"
            "- main_panel_size = <service amps>\\n"
            "- main_breaker_size = <amps>\\n\\n"
            "RAIL SCHEDULE (look for material/equipment schedule tables):\\n"
            "- override_sticks = X  (XR-10-168M, XR-100-204B, or similar rail sticks qty)\\n"
            "- override_splices = X  (splice kit qty)\\n"
            "- If not found: write 'override_sticks = not found'\\n\\n"
            "Keep answers concise. Use the exact labels above so the BOM Calculator can parse them.\\n\\n"
            f"PDF TEXT:\\n{combined_text[:14000]}"
        )

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    except Exception as e:
        return f"Text parsing failed: {e}\\n\\nRaw text:\\n{combined_text[:4000]}"
'''

NEW_DESCRIPTION = (
    "Extract all data from a solar engineering PDF using text-first extraction "
    "(pymupdf4llm markdown + pdfplumber tables). Vision AI is used only as a "
    "fallback for scanned/image-only PDFs. Provide the full absolute Windows file path."
)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    if p["config"]["name"] == "pdf_extractor":
        tools = p["config"]["workbench"]["config"]["tools"]
        for t in tools:
            if t["config"].get("name") == "extract_pdf_data" or "extract_pdf_data" in t["config"].get("source_code", ""):
                t["config"]["source_code"] = NEW_SOURCE
                t["description"] = NEW_DESCRIPTION
                print("Updated extract_pdf_data source code")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Saved to DB.")
