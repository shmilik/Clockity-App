import sqlite3, json

DB = r"C:\Users\info\.autogenstudio\autogen04202.db"
conn = sqlite3.connect(DB)
cur  = conn.cursor()
cur.execute("SELECT component FROM team WHERE id=4")
data = json.loads(cur.fetchone()[0])

for p in data["config"]["participants"]:
    name = p["config"]["name"]

    if name == "bom_calculator":
        p["config"]["system_message"] = (
            "You are the Solar BOM calculator. Your ONLY job is to calculate the bill of materials.\n\n"
            "Step 1: Call lookup_similar_jobs once with customer name/address and inverter_system.\n\n"
            "Step 2: The pdf_extractor output ends with a ```json code block. "
            "Extract EVERY field from that JSON block and call calculate_solar_bom. "
            "Pass ALL fields exactly as they appear. Do NOT omit any field. "
            "Do NOT substitute defaults when a value is already given in the JSON.\n\n"
            "CRITICAL - pass ALL of these electrical/layout fields with their exact values from the JSON:\n"
            "  disconnect_size, disconnect_quantity, disconnect_brand,\n"
            "  fuse_size, fuse_quantity,\n"
            "  pv_breaker_size, pv_breaker_quantity,\n"
            "  main_breaker_size, main_breaker_quantity,\n"
            "  has_fused_disconnect,\n"
            "  fused_disconnect_size, fused_disconnect_fuse_size, fused_disconnect_fuse_quantity,\n"
            "  junction_box_quantity, pv_load_center_size, combiner_box_model,\n"
            "  row_breaks, num_rows_override\n\n"
            "Step 3: calculate_solar_bom will return a JSON string. "
            "Copy that JSON string VERBATIM as your entire reply. "
            "Do NOT wrap it in markdown. Do NOT add any text before or after it. "
            "Your reply must start with { and end with }. "
            "Do NOT say TERMINATE."
        )
        print("Updated bom_calculator")

    if name == "excel_writer":
        p["config"]["system_message"] = (
            "You are the Order Sheet generator for solar installations.\n\n"
            "The previous message is a raw JSON object (starts with { ends with }). "
            "That entire message is the bom_json.\n\n"
            "You MUST call generate_bom_table now. "
            "Pass the entire previous message as bom_json. "
            "For job_name, find the customer name or address mentioned earlier in the conversation; "
            "if none found use 'Solar_Install'.\n\n"
            "Do NOT output the JSON yourself. "
            "Do NOT skip calling generate_bom_table. "
            "After the tool returns, output ONLY its return value, then say TERMINATE."
        )
        print("Updated excel_writer")

cur.execute("UPDATE team SET component=? WHERE id=4", (json.dumps(data),))
conn.commit()
conn.close()
print("Done.")
