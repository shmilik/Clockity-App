"""
Adds a dedicated page 1 array-layout vision call (at 70 DPI) that directly
counts panels, rows, and row_breaks from the rooftop diagram itself.
This is appended to combined_text before the main Claude parsing prompt,
so the parser gets accurate layout values rather than guessing from text.
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    if p["config"]["name"] != "pdf_extractor":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "extract_pdf_data":
            continue
        src = t["config"]["source_code"]

        if "PAGE 1 ARRAY LAYOUT (vision count)" in src:
            print("Array layout vision already present")
            break

        OLD = (
            '    if table_content:\n'
            '        combined_text += "\\n\\n=== EXTRACTED TABLES ===\\n" + table_content\n'
            '\n'
            '    # ── 3. Targeted vision: page 4 electrical single-line diagram ─────────────'
        )
        NEW = (
            '    if table_content:\n'
            '        combined_text += "\\n\\n=== EXTRACTED TABLES ===\\n" + table_content\n'
            '\n'
            '    # ── 2b. Page 1 array layout vision — count panels, rows, breaks ───────────\n'
            '    # Text extraction often misreads panel count and layout geometry.\n'
            '    # A low-DPI full-page vision gives the actual physical row/break count.\n'
            '    page1_layout_analysis = ""\n'
            '    try:\n'
            '        import fitz as _fitz2, base64 as _b64_2\n'
            '        _doc2 = _fitz2.open(pdf_path)\n'
            '        _p1 = _doc2[0]\n'
            '        _mat2 = _fitz2.Matrix(70 / 72, 70 / 72)  # 70 DPI — compact, panel layout still readable\n'
            '        _pix2 = _p1.get_pixmap(matrix=_mat2, colorspace=_fitz2.csRGB)\n'
            '        _p1_b64 = _b64_2.standard_b64encode(_pix2.tobytes("png")).decode("utf-8")\n'
            '        _doc2.close()\n'
            '\n'
            '        import anthropic as _anth2, os as _os2, sys as _sys2\n'
            '        _search2 = [\n'
            '            r"C:\\Users\\info\\OneDrive\\Desktop\\JobTracker",\n'
            '            r"D:\\ResearchTeam-Portable\\app",\n'
            '            r"E:\\ResearchTeam-Portable\\app",\n'
            '        ]\n'
            '        for _d2 in _search2:\n'
            '            if _d2 and _os2.path.isdir(_d2) and _d2 not in _sys2.path:\n'
            '                _sys2.path.insert(0, _d2)\n'
            '        import research_config as _rc2\n'
            '        _client2 = _anth2.Anthropic(api_key=_rc2.ANTHROPIC_API_KEY)\n'
            '\n'
            '        _layout_resp = _client2.messages.create(\n'
            '            model="claude-sonnet-4-5-20250929",\n'
            '            max_tokens=300,\n'
            '            messages=[{"role": "user", "content": [\n'
            '                {"type": "text", "text": (\n'
            '                    "This is page 1 of a solar installation engineering diagram. "\n'
            '                    "Look ONLY at the rooftop array (the main diagram showing panels on the roof). "\n'
            '                    "Count carefully:\\n"\n'
            '                    "- total_panel_count: total individual panels in the ENTIRE array (count every square)\\n"\n'
            '                    "- num_rows: distinct HORIZONTAL rows of panels "\n'
            '                    "(each separate horizontal band = 1 row, "\n'
            '                    "a row split by a gap is STILL 1 row)\\n"\n'
            '                    "- row_breaks: gaps/breaks WITHIN a single horizontal row "\n'
            '                    "(where one row is divided into 2 groups at the same height by an obstacle or gap)\\n"\n'
            '                    "- panels_per_row: panel count in the longest row\\n\\n"\n'
            '                    "Output ONLY a JSON object with exactly these 4 keys. No other text."\n'
            '                )},\n'
            '                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _p1_b64}},\n'
            '            ]}],\n'
            '        )\n'
            '        page1_layout_analysis = _layout_resp.content[0].text.strip()\n'
            '    except Exception:\n'
            '        pass  # silently skip; text analysis still proceeds\n'
            '\n'
            '    if page1_layout_analysis:\n'
            '        combined_text += "\\n\\n=== PAGE 1 ARRAY LAYOUT (vision count) ===\\n" + page1_layout_analysis\n'
            '\n'
            '    # ── 3. Targeted vision: page 4 electrical single-line diagram ─────────────'
        )

        if OLD in src:
            src = src.replace(OLD, NEW)
            print("✅ Inserted page 1 array layout vision call")
        else:
            print("⚠️  Anchor not found")

        try:
            ast.parse(src)
            print("✅ Syntax OK")
        except SyntaxError as e:
            print(f"❌ Syntax error line {e.lineno}: {e.msg}")
            conn.close()
            raise SystemExit(1)
        t["config"]["source_code"] = src

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("✅ Saved.")
