from sentismetric.extract.pdf import extract_digital_page, triage
from sentismetric.analyze.scorecard import extract_flags
from sentismetric.analyze.insights import analyze_filing
from pathlib import Path
import json

pdf_path = str(Path("data/pdfs").rglob("SATHLOKHAR_11082026191510*").__next__())

pages = triage(pdf_path)
full_text = ""
for page_num, is_digital in pages:
    if is_digital:
        text = extract_digital_page(pdf_path, page_num)
        full_text += f"\n\n[Page {page_num}]\n{text}"

flags = extract_flags(full_text)
print("Detected flags:", flags)

result = analyze_filing(full_text, flags=flags)
print(json.dumps(result, indent=2))