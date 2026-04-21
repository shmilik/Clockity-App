"""
Upgrades the Solar BOM Team's extract_pdf_data tool to use vision AI.

The new tool:
1. Extracts all text from the PDF (pymupdf4llm / pdfplumber)
2. Renders every page to an image using PyMuPDF (fitz)
3. Sends text + all page images to Claude vision in a single call
4. Returns a combined analysis that reads both text AND diagrams:
   - panel layout drawings (actual panel count from diagram)
   - equipment callouts and model labels in images
   - single-line electrical diagrams (breaker sizes, fuse, disconnect)
   - roof section labels and mounting notes
"""
import sqlite3, json

DB_PATH = r"C:\Users\info\.autogenstudio\autogen04202.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, component FROM team WHERE id=4")
team_id, component_json = c.fetchone()
team = json.loads(component_json)

# ── New tool source ──────────────────────────────────────────────────────────
NEW_SOURCE = r'''
def extract_pdf_data(pdf_path: str) -> str:
    """Extract text AND visually analyze every page image from a solar engineering PDF.
    Uses vision AI to read roof layout diagrams, panel counts, equipment callouts,
    and single-line electrical drawings that are invisible to text-only parsers.
    Accepts an absolute file path. Returns a comprehensive combined analysis."""
    import os, base64, sys

    if not os.path.exists(pdf_path):
        return f"ERROR: File not found at path: {pdf_path}"

    # ── 1. Extract text ────────────────────────────────────────────────────────
    text_content = ""
    try:
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
        if md and len(md.strip()) > 50:
            text_content = md
    except Exception:
        pass

    if not text_content:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    tables = page.extract_tables() or []
                    tbl = ""
                    for table in tables:
                        for row in table:
                            if row:
                                tbl += " | ".join(str(c) if c else "" for c in row) + "\n"
                    pages.append(f"--- Page {i+1} ---\n{text}\n{tbl}")
            combined = "\n".join(pages)
            if combined.strip():
                text_content = combined
        except Exception as e2:
            text_content = f"Text extraction failed: {e2}"

    # ── 2. Render pages to PNG images using PyMuPDF ────────────────────────────
    page_images_b64 = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(150 / 72, 150 / 72)  # 150 DPI — good quality vs size
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
            page_images_b64.append(b64)
        doc.close()
    except Exception as img_err:
        pass  # fall through to text-only if rendering fails

    # ── 3. Vision analysis: send text + all page images to Claude ─────────────
    if page_images_b64:
        try:
            import anthropic

            # Locate API key — search script dir, JobTracker, and portable paths
            api_key = ""
            search_dirs = [
                r"C:\Users\info\OneDrive\Desktop\JobTracker",
                r"D:\ResearchTeam-Portable\app",
                r"E:\ResearchTeam-Portable\app",
            ]
            for d in search_dirs:
                if d and os.path.isdir(d) and d not in sys.path:
                    sys.path.insert(0, d)
            try:
                import research_config as _cfg
                api_key = _cfg.ANTHROPIC_API_KEY
            except ImportError:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")

            if not api_key:
                return (
                    "Vision analysis skipped: no API key found in research_config or "
                    "ANTHROPIC_API_KEY env variable.\n\nText only:\n\n" + text_content
                )

            client = anthropic.Anthropic(api_key=api_key)

            # Build multi-modal message: instruction + text + all page images
            content = [
                {
                    "type": "text",
                    "text": (
                        "You are analyzing a solar installation engineering / permit sheet PDF. "
                        "The raw extracted text is provided below, followed by images of every page.\n\n"
                        "Analyze BOTH the text AND every page image carefully. Extract the following, "
                        "giving priority to what you can visually see in diagrams when it "
                        "conflicts with the text:\n\n"
                        "QUANTITIES & LAYOUT:\n"
                        "- Total panel count (count individual panels in the roof layout diagram — "
                        "this is more reliable than any number in the text)\n"
                        "- Panel rows and columns, orientation (portrait/landscape per row)\n"
                        "- Which roof sections / facets have panels\n\n"
                        "EQUIPMENT (read model labels in diagrams AND text):\n"
                        "- Panel model number and individual watt rating\n"
                        "- Inverter model, type (string / microinverter / optimizer+inverter), and count\n"
                        "- Optimizer model if present\n"
                        "- Racking / mounting system brand and product line\n"
                        "- Roof type (comp shingle, tile, metal, flat/TPO)\n\n"
                        "ELECTRICAL (read the single-line diagram AND any schedules):\n"
                        "- Main service panel size (amps)\n"
                        "- Main breaker size\n"
                        "- PV breaker size added to existing panel\n"
                        "- AC disconnect type and fuse/breaker size\n"
                        "- Is a new subpanel or main panel upgrade being installed? (Yes/No)\n"
                        "- Wire gauge and conduit type if shown\n\n"
                        "OTHER:\n"
                        "- Any visible special conditions, fire setback annotations, or design notes\n"
                        "- System total DC watts and AC output if labeled\n\n"
                        "If the panel count you see in the diagram differs from a number in the text, "
                        "report both values and flag the discrepancy clearly.\n\n"
                        f"EXTRACTED TEXT:\n{text_content}"
                    ),
                }
            ]

            for i, b64 in enumerate(page_images_b64):
                content.append({"type": "text", "text": f"\n[Page {i + 1}]"})
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                })

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": content}],
            )

            vision_result = response.content[0].text
            return (
                f"VISION + TEXT ANALYSIS  ({len(page_images_b64)} pages read):\n\n"
                f"{vision_result}\n\n"
                f"{'─' * 60}\n"
                f"RAW EXTRACTED TEXT:\n{text_content}"
            )

        except Exception as e:
            # Vision failed — still return text so BOM can proceed
            return (
                f"Vision analysis failed ({type(e).__name__}: {e}). "
                f"Falling back to text only:\n\n{text_content}"
            )

    # ── 4. Text-only fallback (fitz unavailable or 0 pages rendered) ──────────
    if text_content:
        return f"Text extracted (no vision — page rendering unavailable):\n\n{text_content}"

    return "ERROR: Could not extract any content from the PDF."
'''

# Validate source compiles before touching the DB
try:
    compile(NEW_SOURCE, "<string>", "exec")
    print("Source compiles OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    conn.close()
    exit(1)

# Patch the tool in the team JSON
updated = False
for p in team["config"]["participants"]:
    if p["config"]["name"] == "pdf_extractor":
        wb = p["config"].get("workbench", {})
        for t in wb.get("config", {}).get("tools", []):
            if t["config"].get("name") == "extract_pdf_data":
                t["config"]["source_code"] = NEW_SOURCE
                t["description"] = (
                    "Extract text AND visually analyze every page of a solar engineering PDF. "
                    "Reads roof layout diagrams (panel count from drawing), equipment callout labels, "
                    "and single-line electrical diagrams via vision AI. "
                    "Provide the full absolute Windows file path."
                )
                print("Updated extract_pdf_data tool source and description")
                updated = True

if not updated:
    print("WARNING: extract_pdf_data tool not found — check team structure")
    conn.close()
    exit(1)

c.execute("UPDATE team SET component = ? WHERE id = ?", (json.dumps(team), team_id))
conn.commit()
print(f"Saved to database (team id={team_id}).")
conn.close()
