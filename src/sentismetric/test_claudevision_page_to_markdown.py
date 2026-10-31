from sentismetric.extract.pdf import page_to_png
from sentismetric.extract.claude_vision import ClaudeVision

pdf_path = r"data\pdfs\NSE\GANESHINFRA_12082026181933_voting_result-s.pdf"

vision = ClaudeVision()
png_bytes = page_to_png(pdf_path, page_no=2)
markdown = vision.page_to_markdown(png_bytes)

print("=== Page 2 vision output ===")
print(markdown)