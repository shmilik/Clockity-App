import sqlite3, json

DB = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# Get source from pdf_extractor (participant 0, tool 0)
tool = data['config']['participants'][0]['config']['workbench']['config']['tools'][0]
src = tool['config']['source_code']

# ── 1. Insert page 3 racking vision BEFORE the page 4 electrical section ──────
PAGE3_VISION_CODE = r"""
    # ── 2b. Targeted vision: page 3 racking cross-section detail ─────────────
    # Page 3 shows cross-section detail circles labeling the rail brand/model.
    # Text extraction often misses these labels — vision reads them reliably.
    import base64
    page3_racking_analysis = ""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if len(doc) >= 3:
            page = doc[2]  # page 3 (0-indexed)
            mat = fitz.Matrix(90 / 72, 90 / 72)  # 90 DPI — sufficient for labels
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            _p3_b64 = base64.standard_b64encode(pix.tobytes("png")).decode("utf-8")
            doc.close()

            import anthropic, os, sys
            search_dirs = [
                r"C:\Users\info\OneDrive\Desktop\JobTracker",
                r"D:\ResearchTeam-Portable\app",
                r"E:\ResearchTeam-Portable\app",
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
                _rack_resp = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=200,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": (
                            "This is page 3 of a solar permit package. It shows cross-section detail "
                            "circles illustrating how the solar panels attach to the roof.\n\n"
                            "Look for labels (with leader lines/arrows) pointing to the RAIL or RACKING "
                            "component. Examples of what you might see:\n"
                            "  - 'XR10 RAIL' or 'XR100 RAIL' (IronRidge)\n"
                            "  - 'CLICKFIT STANDARD RAIL' or 'CLICKFIT EVOLUTION RAIL' (ClickFit)\n"
                            "  - 'ECOFASTEN NOROOFPENETRATION' or 'ECOFASTEN' product names\n"
                            "  - 'UNIRAC SOLARMOUNT RAIL'\n"
                            "  - 'SOLLEGA' or other brand rails\n\n"
                            "Also look for the ATTACHMENT/FOOT component label (e.g., 'CLICKFIT SMARTFOOT', "
                            "'L-FOOT', 'FLASHFOOT', 'ECOFASTEN ROCK-IT').\n\n"
                            "Output ONLY these two lines (nothing else):\n"
                            "rail_system = <exact brand and product name as written on the diagram>\n"
                            "roof_attachment_hardware = <exact label of the attachment/foot component>\n"
                            "If not visible, write: rail_system = not found"
                        )},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _p3_b64}},
                    ]}],
                )
                page3_racking_analysis = _rack_resp.content[0].text.strip()
        else:
            doc.close()
    except Exception:
        pass  # silently skip; text analysis still proceeds

    if page3_racking_analysis:
        combined_text += "\n\n=== PAGE 3 RACKING DETAIL (vision) ===\n" + page3_racking_analysis

"""

# Insert right before "# ── 3. Targeted vision: page 4 electrical single-line diagram"
ANCHOR = "    # ── 3. Targeted vision: page 4 electrical single-line diagram ─────────────"
if ANCHOR not in src:
    print("ERROR: Could not find page 4 anchor in source. Aborting.")
    conn.close()
    exit(1)

src = src.replace(ANCHOR, PAGE3_VISION_CODE + ANCHOR)
print("✓ Inserted page 3 racking vision code")

# ── 2. Update rail_system JSON field description ───────────────────────────────
OLD_RAIL = '"rail_system (IronRidge XR10|IronRidge XR100|IronRidge QM ClickFit|Unirac SolarMount), "'
NEW_RAIL = (
    '"rail_system (USE PAGE 3 RACKING DETAIL vision value if present — '
    'full brand and product name as labeled on diagram, e.g. \\"IronRidge XR10\\", '
    '\\"IronRidge XR100\\", \\"ClickFit Standard Rail\\", \\"ClickFit Evolution Rail\\", '
    '\\"EcoFasten NoRoof\\", \\"Unirac SolarMount\\" — copy the exact text), "'
)
if OLD_RAIL in src:
    src = src.replace(OLD_RAIL, NEW_RAIL)
    print("✓ Updated rail_system JSON field description")
else:
    print("WARNING: Could not find old rail_system description — may already be updated")

# ── 3. Update the parsing prompt header to mention page 3 ─────────────────────
OLD_PROMPT_HDR = (
    '"The section labelled \'PAGE 4 ELECTRICAL DIAGRAM\' is a vision analysis of the "'
    '    "single-line diagram — prioritize it for disconnect type, fuse size, and interconnection method.\\n\\n" '
)
NEW_PROMPT_HDR = (
    '"The section labelled \'PAGE 3 RACKING DETAIL\' is a vision analysis of the cross-section "'
    '    "detail circles on page 3 — prioritize it for the rail_system and roof attachment hardware.\\n"'
    '    "The section labelled \'PAGE 4 ELECTRICAL DIAGRAM\' is a vision analysis of the "'
    '    "single-line diagram — prioritize it for disconnect type, fuse size, and interconnection method.\\n\\n" '
)
if OLD_PROMPT_HDR in src:
    src = src.replace(OLD_PROMPT_HDR, NEW_PROMPT_HDR)
    print("✓ Updated parsing prompt header")
else:
    # Try alternate quoting
    probe = "PAGE 4 ELECTRICAL DIAGRAM' is a vision analysis of the"
    if probe in src:
        # Find the surrounding line and update it
        idx = src.index(probe)
        # Find the line start
        line_start = src.rfind('"', 0, idx)
        line_end = src.find('\\n\\n"', idx) + len('\\n\\n"')
        old_block = src[line_start:line_end]
        new_block = (
            '"The section labelled \'PAGE 3 RACKING DETAIL\' is a vision analysis of the cross-section '
            'detail circles on page 3 — prioritize it for rail_system and roof attachment hardware.\\n"'
            '    "The section labelled \'PAGE 4 ELECTRICAL DIAGRAM\' is a vision analysis of the '
            'single-line diagram — prioritize it for disconnect type, fuse size, and interconnection method.\\n\\n"'
        )
        src = src[:line_start] + new_block + src[line_end:]
        print("✓ Updated parsing prompt header (alternate match)")
    else:
        print("WARNING: Could not update parsing prompt header — check manually")

# ── 4. Also update the RAIL SCHEDULE section in the prompt to mention page 3 ──
OLD_RAIL_SCHED = '"RAIL SCHEDULE (look for material/equipment schedule tables):\\n"'
NEW_RAIL_SCHED = '"RAIL SCHEDULE (use PAGE 3 RACKING DETAIL vision result if present; also look for material/equipment schedule tables):\\n"'
if OLD_RAIL_SCHED in src:
    src = src.replace(OLD_RAIL_SCHED, NEW_RAIL_SCHED)
    print("✓ Updated RAIL SCHEDULE prompt section")
else:
    print("WARNING: Could not find RAIL SCHEDULE prompt section")

# ── 5. Save back to DB ─────────────────────────────────────────────────────────
tool['config']['source_code'] = src
cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("\nDone — extract_pdf_data updated with page 3 racking vision.")
