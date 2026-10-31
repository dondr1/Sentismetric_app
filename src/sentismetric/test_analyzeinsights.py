from sentismetric.extract.pdf import extract_digital_page

pdf_path = r"data\pdfs\NSE\ACTIVEINFRA_11082026181346_Outcomeoftheboardmeetingsd.pdf"

full_text = ""
for page_num in range(1, 8):
    text = extract_digital_page(pdf_path, page_num)
    full_text += f"\n\n[Page {page_num}]\n{text}"

print(f"Total markdown length: {len(full_text)} chars")

from sentismetric.analyze.insights import analyze_filing
result = analyze_filing(full_text)

import json
print(json.dumps(result, indent=2))