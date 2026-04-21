import sqlite3, json

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
d = json.loads(cur.fetchone()[0])

for p in d["config"]["participants"]:
    name = p["config"]["name"]

    if name == "bom_calculator":
        p["config"]["system_message"] = (
            "You are the Solar BOM calculator. Your ONLY job is to calculate the bill of materials.\n\n"
            "Step 1: Call lookup_similar_jobs once with customer name/address and inverter_system.\n\n"
            "Step 2: The pdf_extractor output ends with a ```json code block. "
            "Extract EVERY field from that JSON block and call calculate_solar_bom. "
            "Pass ALL fields exactly as they appear - do NOT omit any field, do NOT substitute defaults.\n\n"
            "CRITICAL - pass ALL of these if non-zero/non-empty in the JSON:\n"
            "  disconnect_size, disconnect_quantity, disconnect_brand,\n"
            "  fuse_size, fuse_quantity,\n"
            "  pv_breaker_size, pv_breaker_quantity,\n"
            "  main_breaker_size, main_breaker_quantity,\n"
            "  has_fused_disconnect,\n"
            "  fused_disconnect_size, fused_disconnect_fuse_size, fused_disconnect_fuse_quantity,\n"
            "  junction_box_quantity, pv_load_center_size, combiner_box_model,\n"
            "  row_breaks, num_rows_override\n\n"
            "Step 3: After calculate_solar_bom returns its JSON, output ONLY this block:\n\n"
            "BOM_RESULT_START\n"
            "{the full JSON returned by calculate_solar_bom}\n"
            "BOM_RESULT_END\n\n"
            "No other text. Do NOT say TERMINATE."
        )
        print("Updated bom_calculator")

    if name == "excel_writer":
        p["config"]["system_message"] = (
            "You are the Order Sheet generator for solar installations.\n\n"
            "The previous agent's message contains a JSON block between the markers "
            "BOM_RESULT_START and BOM_RESULT_END. "
            "Extract everything between those markers as the bom_json argument.\n\n"
            "If those markers are not present, look for any JSON object with a 'bom' key "
            "in the conversation and use that.\n\n"
            "ALWAYS call generate_bom_table with:\n"
            "  bom_json = the full JSON string (including the summary and bom keys)\n"
            "  job_name = the customer name or address from the engineering sheet "
            "(default to 'Solar_Install' if not found)\n\n"
            "Output ONLY what generate_bom_table returns. No extra text. Then say TERMINATE."
        )
        print("Updated excel_writer")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(d),))
conn.commit()
conn.close()
print("Done.")
