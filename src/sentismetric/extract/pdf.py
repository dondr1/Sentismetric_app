import fitz
from dataclasses import dataclass

@dataclass
class PageText:
    page: int
    text: str
    method: str

def triage(pdf_path: str) -> list[tuple[int, bool]]:
    """Return [(page_number, is_digital)] by text density."""
    out =[]
    with fitz.open(pdf_path) as doc:
        for i , page in enumerate(doc, start=1):
            chars = len(page.get_text("text").strip())
            out.append((i,chars>200)) # this threshold can be tuned based on real filings
    return out

def extract_digital_page(pdf_path: str, page_no: int) -> str:
    with fitz.open(pdf_path) as doc:
        return doc[page_no-1].get_text("text")

def page_to_png(pdf_path: str, page_no: int, dpi: int = 180) -> bytes:
    with fitz.open(pdf_path) as doc:
        pix = doc[page_no - 1].get_pixmap(dpi=dpi)
        return pix.tobytes("png")     

def chunk_pages(pages: list[PageText], target: int = 1000, overlap: int = 150):
    """Split page texts into ~target-token chunks with overlap,
    keeping page tags."""
    chunks = []
    current_words = []
    current_page_start = None

    for p in pages:
        words = p.text.split()
        for word in words:
            if current_page_start is None:
                current_page_start = p.page

            current_words.append(word)

            current_text = " ".join(current_words)
            estimated_tokens = len(current_text) / 4

            if estimated_tokens >= target:
                chunks.append({
                    "text": current_text,
                    "page_start": current_page_start,
                    "page_end": p.page,
                })

                #keep roughly `overlap` tokens' worth of words for the next chunk
                overlap_chars = 0
                overlap_words = []
                for w in reversed(current_words):
                    overlap_chars += len(w) + 1
                    overlap_words.insert(0, w)
                    if overlap_chars / 4 >= overlap:
                        break
                current_words = overlap_words
                current_page_start = p.page

    #flush whatever's left as the final chunk
    if current_words:
        chunks.append({
            "text": " ".join(current_words),
            "page_start": current_page_start,
            "page_end": pages[-1].page if pages else None,
        })

    return chunks