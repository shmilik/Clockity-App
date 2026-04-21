import pymupdf4llm
import os

pdf_path = r"C:\Users\info\OneDrive\Desktop\Engi\documents_v1_drawing-set_1738 Hays St NW - Solar PV Plans.pdf"

print(f"File exists: {os.path.exists(pdf_path)}")
print(f"File size: {os.path.getsize(pdf_path):,} bytes")
print()

try:
    print("Trying pymupdf4llm...")
    md = pymupdf4llm.to_markdown(pdf_path, show_progress=False)
    print(f"SUCCESS - extracted {len(md)} characters")
    print("\n--- First 3000 chars ---")
    print(md[:3000])
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
