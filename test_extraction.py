from sentismetric.extract.pdf import triage, extract_digital_page, page_to_png, PageText, chunk_pages
from sentismetric.extract.claude_vision import ClaudeVision

pdf_path = r"data\pdfs\NSE\ACTIVEINFRA_11082026181346_Outcomeoftheboardmeetingsd.pdf"

# Step 1: triage
pages = triage(pdf_path)
print("=== Triage results ===")
for page_num, is_digital in pages:
    print(f"  page {page_num}: {'digital' if is_digital else 'scanned'}")

# Step 2: extract each page using the right method
page_texts = []
vision = ClaudeVision()

for page_num, is_digital in pages:
    if is_digital:
        text = extract_digital_page(pdf_path, page_num)
        method = "digital"
    else:
        png_bytes = page_to_png(pdf_path, page_num)
        text = vision.page_to_markdown(png_bytes)
        method = "vision"
    page_texts.append(PageText(page=page_num, text=text, method=method))
    print(f"\n=== Page {page_num} ({method}) - first 300 chars ===")
    print(text[:300])

# Step 3: chunk everything
chunks = chunk_pages(page_texts)
print(f"\n=== Produced {len(chunks)} chunks ===")
for c in chunks:
    print(f"  pages {c['page_start']}-{c['page_end']}: {len(c['text'])} chars")