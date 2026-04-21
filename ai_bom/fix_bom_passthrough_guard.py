"""
Fixes generate_bom_table to detect when it receives the raw pdf_extractor params JSON
(panel_count key present, no bom key) and auto-calls calculate_solar_bom itself.
This makes the pipeline resilient even if bom_calculator skips the tool call.
"""
import sqlite3, json, ast

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    if p["config"]["name"] != "excel_writer":
        continue
    for t in p["config"].get("workbench", {}).get("config", {}).get("tools", []):
        if t["config"]["name"] != "generate_bom_table":
            continue
        src = t["config"]["source_code"]

        OLD = (
            '    items = bom if isinstance(bom, list) else bom.get("items", bom.get("bom", []))\n'
            '\n'
            '    # ── Build markdown table ──'
        )
        NEW = (
            '    # If bom_calculator passed the raw pdf_extractor params dict instead of\n'
            '    # calling calculate_solar_bom, auto-calculate the BOM from those params.\n'
            '    if isinstance(bom, dict) and "panel_count" in bom and "bom" not in bom and "items" not in bom:\n'
            '        import sys, os\n'
            '        _search = [\n'
            '            r"C:\\Users\\info\\OneDrive\\Desktop\\JobTracker",\n'
            '            r"D:\\ResearchTeam-Portable\\app",\n'
            '            r"E:\\ResearchTeam-Portable\\app",\n'
            '        ]\n'
            '        for _d in _search:\n'
            '            if _d and os.path.isdir(_d) and _d not in sys.path:\n'
            '                sys.path.insert(0, _d)\n'
            '        try:\n'
            '            import sqlite3 as _sq3, json as _jj\n'
            '            _db = r"C:\\Users\\info\\.autogenstudio\\autogen04202.db"\n'
            '            _c2 = _sq3.connect(_db).cursor()\n'
            '            _c2.execute("SELECT component FROM team WHERE id=4")\n'
            '            _td = _jj.loads(_c2.fetchone()[0])\n'
            '            _bom_src = None\n'
            '            for _pp in _td["config"]["participants"]:\n'
            '                if _pp["config"]["name"] != "bom_calculator": continue\n'
            '                for _tt in _pp["config"].get("workbench",{}).get("config",{}).get("tools",[]):\n'
            '                    if _tt["config"]["name"] == "calculate_solar_bom":\n'
            '                        _bom_src = _tt["config"]["source_code"]\n'
            '            if _bom_src:\n'
            '                _g = {"json": _jj}\n'
            '                exec(_bom_src, _g)\n'
            '                _fn = _g["calculate_solar_bom"]\n'
            '                _params = {k: v for k, v in bom.items()\n'
            '                           if k in _fn.__code__.co_varnames}\n'
            '                _result = _jj.loads(_fn(**_params))\n'
            '                bom = _result\n'
            '        except Exception as _auto_err:\n'
            '            pass  # fall through to empty items\n'
            '\n'
            '    items = bom if isinstance(bom, list) else bom.get("items", bom.get("bom", []))\n'
            '\n'
            '    # ── Build markdown table ──'
        )

        if "panel_count" in src and "auto-calculate the BOM" in src:
            print("Already patched — skipping")
        elif OLD in src:
            src = src.replace(OLD, NEW)
            try:
                ast.parse(src)
                print("✅ Patched generate_bom_table; syntax OK")
            except SyntaxError as e:
                print(f"❌ Syntax error line {e.lineno}: {e.msg}")
                conn.close()
                raise SystemExit(1)
            t["config"]["source_code"] = src
        else:
            print("⚠️  Anchor not found")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("✅ Saved.")
