"""
WEEK 2 head start: extract text from a PDF, page by page, with PyMuPDF.

The key idea: we keep the PAGE NUMBER with every chunk of text. Later (Week 7)
you'll also keep character/coordinate positions so the frontend can highlight
the exact source of each obligation. That traceability is the product's moat.

Run it:
    python ingestion/extract_pdf.py data/samples/your-file.pdf

Docs: https://pymupdf.readthedocs.io/en/latest/the-basics.html
"""

from dataclasses import dataclass

import fitz  # this is PyMuPDF


@dataclass
class PageText:
    """Text from one page, tagged with where it came from."""
    page_number: int          # 1-based, human-friendly
    text: str


def extract_pages(pdf_path: str) -> list[PageText]:
    """Return a list of PageText, one per page of the PDF."""
    pages: list[PageText] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            pages.append(PageText(page_number=i + 1, text=page.get_text()))
    return pages


def main(pdf_path: str) -> None:
    pages = extract_pages(pdf_path)
    print(f"Extracted {len(pages)} pages from {pdf_path}\n")
    for page in pages:
        print(f"--- Page {page.page_number} ---")
        # Print just the first 400 characters so the terminal isn't flooded
        preview = page.text.strip()[:400]
        print(preview or "(no extractable text — may be a scanned image; OCR comes in Week 10)")
        print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python ingestion/extract_pdf.py <path-to-pdf>")
        print("Tip: download a solicitation from https://sam.gov into data/samples/")
        sys.exit(1)

    main(sys.argv[1])
