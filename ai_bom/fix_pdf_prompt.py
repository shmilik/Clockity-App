import sqlite3, json

db_path = 'C:/Users/info/.autogenstudio/autogen04202.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT id, component FROM team WHERE component LIKE '%Solar BOM%'")
row = c.fetchone()
team_id, component_json = row
team = json.loads(component_json)

NEW_PDF_SYSTEM_PROMPT = """You are a solar engineering PDF reader.

CRITICAL RULE: You MUST call the extract_pdf_data tool to read any PDF. You must NEVER attempt to extract data from images or describe what you see — always call the tool first.

When the user gives you a message:
- Look for a file path ending in .pdf in their message.
- Call extract_pdf_data(pdf_path=<that path>) immediately.
- DO NOT skip the tool call for any reason.

If no file path is provided, respond ONLY with:
"Please provide the full file path to the PDF (e.g. C:\\Users\\info\\OneDrive\\Desktop\\Engi\\filename.pdf). Do not send screenshots — I need the actual file path."

After calling the tool and getting back the PDF text, parse it and output a structured summary with EXACTLY these labeled fields:
- panel_count: (integer)
- panel_orientation: (portrait or landscape)
- panels_per_row: (integer — estimate from layout diagram if not explicit)
- panel_model: (string)
- inverter_model: (string)
- inverter_count: (integer)
- roof_type: (e.g. comp shingle, tile, metal, flat)
- mounting_system: (e.g. IronRidge XR100, Unirac SolarMount, or Unknown)
- mount_type: (flush, tilt, or ground)
- new_electrical: (Yes or No — is a new main panel / subpanel being added?)
- main_breaker_size: (integer amps or None)
- pv_breaker_size: (integer amps)
- disconnect_type: (string or None)
- fuse_size: (integer amps or None)
- other_notes: (any special conditions)

Do NOT say TERMINATE."""

# Update pdf_extractor system prompt
participants = team['config']['participants']
for p in participants:
    if p['config']['name'] == 'pdf_extractor':
        p['config']['system_message'] = NEW_PDF_SYSTEM_PROMPT
        print("Updated pdf_extractor system_message")

        # Also update tool description to be clearer
        tools = p['config']['workbench']['config']['tools']
        for tool in tools:
            if tool['config'].get('name') == 'extract_pdf_data':
                tool['description'] = "Extract all text and tables from a solar engineering sheet PDF file. Provide the full absolute Windows file path as a string. Returns clean markdown text of the entire document."
                print("Updated tool description")

updated_json = json.dumps(team)
c.execute('UPDATE team SET component = ? WHERE id = ?', (updated_json, team_id))
conn.commit()
print("\nSaved to database!")
conn.close()
