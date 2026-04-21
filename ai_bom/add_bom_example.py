"""
Adds a verified completed job to the BOM example store.

Usage:
    python add_bom_example.py

The script will prompt you for the job details interactively,
or you can import add_example() and call it directly.
"""
import json
import os
import uuid
from datetime import date

STORE_PATH = os.path.join(
    os.path.dirname(__file__), "instance", "bom_examples.json"
)


def load_store():
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_store(store):
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def add_example(
    job_name: str,
    panel_count: int,
    panel_orientation: str,
    panels_per_row: int,
    panel_width_in: float,
    panel_height_in: float,
    rail_system: str,
    roof_attachment: str,
    verified_bom: list,
    notes: str = "",
):
    """
    Add a verified job to the example store.

    verified_bom should be a list of dicts:
      [{"description": "...", "qty": 10, "unit": "EA"}, ...]
    """
    store = load_store()
    entry = {
        "id": "job-" + str(uuid.uuid4())[:8],
        "added": date.today().isoformat(),
        "job_name": job_name,
        "inputs": {
            "panel_count": panel_count,
            "panel_orientation": panel_orientation,
            "panels_per_row": panels_per_row,
            "panel_width_in": panel_width_in,
            "panel_height_in": panel_height_in,
            "rail_system": rail_system,
            "roof_attachment": roof_attachment,
        },
        "verified_bom": verified_bom,
        "notes": notes,
        "verified": True,
    }
    store["examples"].append(entry)
    save_store(store)
    print(f"Added example '{job_name}' (id={entry['id']}) to {STORE_PATH}")
    return entry["id"]


def interactive_add():
    print("\n=== Add Verified BOM Example ===\n")
    job_name         = input("Job name:                        ").strip()
    panel_count      = int(input("Panel count:                     "))
    panel_orientation = input("Orientation (portrait/landscape): ").strip().lower()
    panels_per_row   = int(input("Panels per row:                  "))
    panel_width_in   = float(input("Panel width in inches [40.9]:    ") or "40.9")
    panel_height_in  = float(input("Panel height in inches [67.9]:   ") or "67.9")
    rail_system      = input("Rail system [IronRidge XR100]:   ").strip() or "IronRidge XR100"
    roof_attachment  = input("Roof type [comp_shingle]:        ").strip() or "comp_shingle"
    notes            = input("Notes (optional):                ").strip()

    print("\nNow enter the VERIFIED BOM line items.")
    print("Format: description | qty   (e.g.  Rail Sticks (10ft) | 16)")
    print("Press Enter with no input when done.\n")

    bom_lines = []
    while True:
        line = input("  Item: ").strip()
        if not line:
            break
        if "|" not in line:
            print("  Skipping — use 'description | qty' format.")
            continue
        parts = line.split("|", 1)
        try:
            bom_lines.append({
                "description": parts[0].strip(),
                "qty": int(parts[1].strip()),
                "unit": "EA",
            })
        except ValueError:
            print("  Skipping — qty must be an integer.")

    if not bom_lines:
        print("No BOM lines entered — aborting.")
        return

    entry_id = add_example(
        job_name=job_name,
        panel_count=panel_count,
        panel_orientation=panel_orientation,
        panels_per_row=panels_per_row,
        panel_width_in=panel_width_in,
        panel_height_in=panel_height_in,
        rail_system=rail_system,
        roof_attachment=roof_attachment,
        verified_bom=bom_lines,
        notes=notes,
    )
    print(f"\nSaved as {entry_id}. Total examples: {len(load_store()['examples'])}")


if __name__ == "__main__":
    interactive_add()
