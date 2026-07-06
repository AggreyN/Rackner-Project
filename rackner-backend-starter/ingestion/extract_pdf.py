"""
WEEK 2 head start: extract text from a PDF, page by page, with PyMuPDF.

The key idea: we keep the PAGE NUMBER with every chunk of text. Later (Week 7)
you'll also keep character/coordinate positions so the frontend can highlight
the exact source of each obligation. That traceability is the product's moat.

Run it:
    python ingestion/extract_pdf.py data/samples/your-file.pdf

Docs: https://pymupdf.readthedocs.io/en/latest/the-basics.html
"""

# `dataclass` is a shortcut for making a simple "data holder" class: you declare
# the fields and Python writes the boilerplate (__init__, __repr__, etc.) for you.
from dataclasses import dataclass

import fitz  # PyMuPDF's import name is "fitz" (a historical quirk of the library)


@dataclass
class PageText:
    """Text from one page, tagged with where it came from.

    Bundling the text together with its page number is the whole point: every
    piece of text stays linked to its source so we can trace an obligation back
    to the exact page it came from.
    """
    page_number: int          # 1-based, human-friendly (page 1 = first page)
    text: str                 # all the text PyMuPDF could pull off that page


def extract_pages(pdf_path: str) -> list[PageText]:
    """Open a PDF and return its text as a list of PageText — one item per page."""
    pages: list[PageText] = []          # start with an empty list we'll fill up
    # `with fitz.open(...)` opens the PDF and guarantees it's closed afterward,
    # even if something errors partway through.
    with fitz.open(pdf_path) as doc:
        # Looping over `doc` yields each page in order. `enumerate` also hands us
        # a counter `i` starting at 0, so `i + 1` gives the human page number.
        for i, page in enumerate(doc):
            # `page.get_text()` returns all the selectable text on that page as
            # a single string. We wrap it in a PageText so the page number rides along.
            pages.append(PageText(page_number=i + 1, text=page.get_text()))
    return pages                         # hand the finished list back to the caller


def main(pdf_path: str) -> None:
    """Extract the PDF and print a short preview of each page to the terminal."""
    pages = extract_pages(pdf_path)      # do the actual extraction
    print(f"Extracted {len(pages)} pages from {pdf_path}\n")
    # Walk through every page and show what we got.
    for page in pages:
        print(f"--- Page {page.page_number} ---")
        # `.strip()` trims surrounding whitespace; `[:400]` keeps only the first
        # 400 characters so a long page doesn't flood the terminal.
        preview = page.text.strip()[:400]
        # `preview or "..."`: if `preview` is empty (a blank string is "falsy"),
        # fall back to the message. Empty text usually means the page is a scanned
        # image, which needs OCR — that comes in Week 10.
        print(preview or "(no extractable text — may be a scanned image; OCR comes in Week 10)")
        print()                          # blank line between pages for readability


# This block only runs when you execute the file directly (not when it's
# imported by other code). It reads the PDF path from the command line.
if __name__ == "__main__":
    import sys                           # `sys.argv` holds the command-line arguments

    # sys.argv[0] is the script name, so a valid call has exactly 2 items:
    # the script + one PDF path. Anything else means the user called it wrong.
    if len(sys.argv) != 2:
        print("Usage: python ingestion/extract_pdf.py <path-to-pdf>")
        print("Tip: download a solicitation from https://sam.gov into data/samples/")
        sys.exit(1)                      # exit with code 1 to signal an error

    main(sys.argv[1])                    # sys.argv[1] is the PDF path the user typed
