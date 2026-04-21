import sqlite3, json

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

# 1. Lower max_messages from 20 to 9
for cond in data["config"]["termination_condition"]["config"]["conditions"]:
    if "max_messages" in cond.get("config", {}):
        old = cond["config"]["max_messages"]
        cond["config"]["max_messages"] = 9
        print(f"max_messages: {old} -> 9")

# 2. Tighten each agent's system message so it exits cleanly after one pass
for p in data["config"]["participants"]:
    name = p["config"]["name"]
    if name == "pdf_extractor":
        p["config"]["system_message"] = (
            "You are the PDF extraction agent for solar installation jobs. "
            "Call extract_pdf_data ONCE with the PDF file path provided by the user. "
            "Pass the extracted JSON result directly to the next agent without any extra commentary. "
            "Do NOT call the tool again or repeat any work."
        )
        print("Updated pdf_extractor system_message")
    elif name == "bom_calculator":
        p["config"]["system_message"] = (
            "You are the Solar BOM calculator. "
            "Call lookup_similar_jobs once with the system type and address from the extracted data. "
            "Then call calculate_solar_bom once with all relevant fields from the extracted data. "
            "Pass the resulting BOM JSON directly to the next agent. "
            "Do NOT repeat tool calls or add extra commentary."
        )
        print("Updated bom_calculator system_message")
    elif name == "excel_writer":
        p["config"]["system_message"] = (
            "You are the Order Sheet generator for solar installations. "
            "Call generate_bom_table ONCE with the BOM JSON and the job name from the engineering sheet. "
            "Output only the table returned by the tool and the Excel file path. "
            "Do not add any extra text. Then say TERMINATE."
        )
        print("Updated excel_writer system_message")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Saved successfully.")
