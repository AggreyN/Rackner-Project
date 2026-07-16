"""WEEK 2: extract text from a PDF, page by page, WITH word coordinates.

The key idea: we keep the PAGE NUMBER *and* the position of every word with
each chunk of text. That coordinate trail (page → char offset → pixel box) is
what lets the frontend highlight the exact source of each obligation. That
traceability is the product's moat.

How the pieces line up
----------------------
PyMuPDF gives us two views of a page: a plain-text blob (`page.get_text()`) and
a list of words each with a bounding box (`page.get_text("words")`). Their
character positions do NOT line up with each other, so instead of trusting the
plain blob we **rebuild the page text from the word list**. Every word then
knows its exact character range inside `PageText.text`, so any character span
(e.g. a clause's `char_start..char_end` from segment.py) maps straight back to a
set of pixel boxes via `boxes_for_span`.

Run it:
    python ingestion/extract_pdf.py data/samples/your-file.pdf

Docs: https://pymupdf.readthedocs.io/en/latest/recipes-text.html
"""

from dataclasses import dataclass, field

import fitz  # this is PyMuPDF


@dataclass
class Word:
    """One word and where it sits — on the page image and in the page string."""
    text: str
    char_start: int          # offset into the owning PageText.text (inclusive)
    char_end: int            # offset into the owning PageText.text (exclusive)
    x0: float                # bounding box, PDF points, origin top-left
    y0: float
    x1: float
    y1: float

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass
class PageText:
    """Text from one page, tagged with where it came from.

    `text` is reconstructed from `words`, so a slice `text[a:b]` corresponds
    exactly to the words whose char ranges fall in [a, b) — see boxes_for_span.
    """
    page_number: int                     # 1-based, human-friendly
    text: str
    words: list[Word] = field(default_factory=list)


def _extract_words(page) -> tuple[str, list[Word]]:
    """Rebuild a page's text from its word boxes, tracking char offsets.

    Returns (text, words). Words on the same line are joined by a single space,
    lines by a newline — so offsets stay dense and predictable. `sort=True` puts
    the words in natural reading order (top-to-bottom, left-to-right).
    """
    # Each tuple: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
    raw = page.get_text("words", sort=True)

    parts: list[str] = []
    words: list[Word] = []
    cursor = 0
    prev_line: tuple[int, int] | None = None

    for x0, y0, x1, y1, w, block_no, line_no, _word_no in raw:
        line = (block_no, line_no)
        if prev_line is None:
            sep = ""
        elif line != prev_line:
            sep = "\n"          # new line or new block → line break
        else:
            sep = " "           # same line → space between words
        if sep:
            parts.append(sep)
            cursor += len(sep)

        start = cursor
        parts.append(w)
        cursor += len(w)
        words.append(Word(text=w, char_start=start, char_end=cursor,
                          x0=x0, y0=y0, x1=x1, y1=y1))
        prev_line = line

    return "".join(parts), words


def extract_pages(pdf_path: str) -> list[PageText]:
    """Return a list of PageText, one per page of the PDF, with word boxes.

    For a page that has no extractable word layer (e.g. a scanned image), the
    word list is empty and we fall back to `get_text()` so downstream code still
    sees whatever text is there. OCR for truly image-only pages is Week 7.
    """
    pages: list[PageText] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text, words = _extract_words(page)
            if not text:
                text = page.get_text()  # scanned page — no words to box
            pages.append(PageText(page_number=i + 1, text=text, words=words))
    return pages


def boxes_for_span(page: PageText, char_start: int, char_end: int) -> list[tuple[float, float, float, float]]:
    """Map a character span in `page.text` to the word boxes it covers.

    This is the payoff of tracking coordinates: give it a clause's or an
    obligation's char range and it returns the pixel rectangles to highlight.
    A word counts if it overlaps [char_start, char_end) at all.
    """
    return [
        w.bbox
        for w in getattr(page, "words", [])
        if w.char_start < char_end and w.char_end > char_start
    ]


def main(pdf_path: str) -> None:
    pages = extract_pages(pdf_path)
    total_words = sum(len(p.words) for p in pages)
    print(f"Extracted {len(pages)} pages ({total_words} words) from {pdf_path}\n")
    for page in pages:
        print(f"--- Page {page.page_number} — {len(page.words)} words ---")
        preview = page.text.strip()[:400]
        print(preview or "(no extractable text — likely a scanned image; OCR is Week 7)")
        if page.words:
            w = page.words[0]
            print(f"    e.g. first word {w.text!r} chars[{w.char_start}:{w.char_end}] "
                  f"box=({w.x0:.0f},{w.y0:.0f},{w.x1:.0f},{w.y1:.0f})")
        print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python ingestion/extract_pdf.py <path-to-pdf>")
        print("Tip: download a solicitation from https://sam.gov into data/samples/")
        sys.exit(1)

    main(sys.argv[1])
