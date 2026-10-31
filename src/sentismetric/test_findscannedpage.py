from pathlib import Path
from sentismetric.extract.pdf import triage

pdf_dir = Path("data/pdfs")
found = False

for pdf_path in pdf_dir.rglob("*.pdf"):
    try:
        pages = triage(str(pdf_path))
    except Exception as e:
        print(f"failed to triage {pdf_path.name}: {e}")
        continue

    scanned_pages = [p for p, is_digital in pages if not is_digital]
    if scanned_pages:
        print(f"FOUND: {pdf_path} has scanned pages: {scanned_pages}")
        found = True

if not found:
    print("No scanned pages found across any downloaded PDF.")