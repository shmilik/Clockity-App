
def generate_bom_table(bom_json: str, job_name: str = "Solar_Install") -> str:
    """Format the solar BOM as a markdown table visible in chat, and create
    a Google Sheet via Apps Script web app shared to apais@unicitysolar.com.
    Returns the markdown table + the Google Sheet URL."""
    import json as _json, os

    WORK_EMAIL = "apais@unicitysolar.com"

    # Paste your Apps Script web app URL here after deploying it.
    # It stays in a plain text file so it is easy to update without touching the DB.
    APPS_SCRIPT_URL = ""
    url_file_paths = [
        "C:\\Users\\info\\OneDrive\\Desktop\\JobTracker\\apps_script_url.txt",
        "D:\\ResearchTeam-Portable\\app\\apps_script_url.txt",
        "E:\\ResearchTeam-Portable\\app\\apps_script_url.txt",
    ]
    for _p in url_file_paths:
        if os.path.exists(_p):
            with open(_p, encoding="utf-8-sig") as _f:  # utf-8-sig strips BOM automatically
                APPS_SCRIPT_URL = _f.read().strip()
            break

    # ── MFR code lookup ───────────────────────────────────────────────────────
    def mfr_for(cat):
        cat = (cat or "").upper()
        if any(x in cat for x in ["XR10","XR100","XR-10","XR-100","QM-CF","ICON","IRD","IRID"]):
            return "IRIDG"
        if any(x in cat for x in ["Q.PEAK","Q.CELLS","QPEAK","QCELL","BLK"]):
            return "QCELL"
        if any(x in cat for x in ["IQ8","IQ7","IQ6","Q-CABLE","QCABLE","ENPHASE","ENV"]):
            return "ENP"
        if any(x in cat for x in ["BR220","BR1515","BR115","BR130","CH220","QO220","EATON","CUTLER"]):
            return "EATON"
        if any(x in cat for x in ["TY-RAP","TYRAP","TYTON","ZIP","CABLE TIE"]):
            return "TYTON"
        if any(x in cat for x in ["LAY","LAYO","GRND","GROUND LUG","GND"]):
            return "ERICO"
        return "MISC"

    # ── Parse BOM JSON ────────────────────────────────────────────────────────
    try:
        if isinstance(bom_json, dict):
            bom = bom_json
        else:
            bom_json = bom_json.strip()
            if bom_json.startswith("```"):
                bom_json = "\n".join(
                    ln for ln in bom_json.splitlines()
                    if not ln.strip().startswith("```")
                )
            bom = _json.loads(bom_json)
    except Exception as e:
        return f"ERROR parsing BOM JSON: {e}\n\nRaw input:\n{bom_json}"

    items = bom if isinstance(bom, list) else bom.get("items", bom.get("bom", []))

    # ── Build markdown table ──────────────────────────────────────────────────
    header = f"## Solar BOM -- {job_name}\n\n"
    header += "| # | MFR | Catalog # | Description | Qty | Unit |\n"
    header += "|---|-----|-----------|-------------|-----|------|\n"
    rows_md   = []
    rows_data = []
    for i, item in enumerate(items, 1):
        cat  = str(item.get("catalog_number", item.get("part_number", item.get("sku", "")))).strip()
        desc = str(item.get("description", item.get("name", ""))).strip()
        qty  = item.get("quantity", item.get("qty", ""))
        unit = str(item.get("unit", "EA")).strip()
        mfr  = mfr_for(cat)
        rows_md.append(f"| {i} | {mfr} | {cat} | {desc} | {qty} | {unit} |")
        rows_data.append({"seq": i, "mfr": mfr, "catalog": cat,
                          "description": desc, "qty": qty, "unit": unit})

    md_table = header + "\n".join(rows_md)

    # ── Post to Google Apps Script web app ────────────────────────────────────
    if not APPS_SCRIPT_URL:
        return (
            md_table +
            "\n\n> **Google Sheet not created** -- Apps Script URL not configured.\n"
            "> Save your web app URL to `apps_script_url.txt` in the JobTracker folder."
        )

    try:
        import urllib.request, urllib.error, json as _json2

        payload = _json2.dumps({
            "job_name": job_name,
            "email":    WORK_EMAIL,
            "bom":      rows_data,
        }).encode("utf-8")

        # Apps Script returns a 302 after processing the POST.
        # The redirect must be followed as GET (standard 302 behaviour).
        # The data is already processed before the redirect ─ the redirect
        # just delivers the JSON response body.
        class _GetRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return urllib.request.Request(newurl, method="GET")

        opener = urllib.request.build_opener(_GetRedirect())
        req = urllib.request.Request(
            APPS_SCRIPT_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(req, timeout=35) as resp:
            result = _json2.loads(resp.read().decode("utf-8"))

        if "url" in result:
            return md_table + f"\n\n**Google Sheet:** {result['url']}"
        else:
            return md_table + f"\n\n> Google Sheet export failed: {result.get('error', result)}"

    except Exception as post_err:
        return md_table + f"\n\n> Google Sheet export failed: {post_err}"
