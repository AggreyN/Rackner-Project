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

Scanned (image-only) pages have no word layer. Week 7 adds an OCR fallback:
if `pytesseract` + the `tesseract` binary are installed we OCR the page and get
words *with* boxes, so scanned pages join the same coordinate system. Without
them the page simply comes back empty — OCR is optional, never required.

Run it:
    python ingestion/extract_pdf.py data/samples/your-file.pdf

Docs: https://pymupdf.readthedocs.io/en/latest/recipes-text.html
"""

import os
import re
from dataclasses import dataclass, field

import fitz  # this is PyMuPDF

# Render resolution for OCR. Higher = better accuracy, slower.
OCR_DPI = int(os.getenv("OCR_DPI", "200"))


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
    ocr: bool = False                    # True if this page's text came from OCR


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


def _ocr_words(page) -> tuple[str, list[Word]]:
    """OCR one page that has no text layer, returning text + boxed words.

    Optional by design: if `pytesseract`/`Pillow` aren't installed, or the
    `tesseract` binary is missing, we return ("", []) and the caller carries on.
    A missing OCR toolchain must never break ingestion of normal PDFs.

    Enable with:  pip install pytesseract pdf2image  &&  brew install tesseract
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", []

    try:
        pix = page.get_pixmap(dpi=OCR_DPI)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        # tesseract binary absent, or it failed on this page — degrade quietly.
        return "", []

    scale = 72.0 / OCR_DPI          # image pixels → PDF points, so OCR boxes
    parts: list[str] = []           # share one coordinate system with the text layer
    words: list[Word] = []
    cursor = 0
    prev_line: tuple[int, int, int] | None = None

    for i, raw_word in enumerate(data["text"]):
        w = (raw_word or "").strip()
        if not w:
            continue
        line = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        sep = "" if prev_line is None else ("\n" if line != prev_line else " ")
        if sep:
            parts.append(sep)
            cursor += len(sep)

        start = cursor
        parts.append(w)
        cursor += len(w)
        x, y = data["left"][i], data["top"][i]
        dx, dy = data["width"][i], data["height"][i]
        words.append(Word(text=w, char_start=start, char_end=cursor,
                          x0=x * scale, y0=y * scale,
                          x1=(x + dx) * scale, y1=(y + dy) * scale))
        prev_line = line

    return "".join(parts), words


def extract_pages(pdf_path: str) -> list[PageText]:
    """Return a list of PageText, one per page of the PDF, with word boxes.

    A page with no word layer (a scanned image) falls back to OCR when it's
    available, so scanned pages end up in the same page→char→box coordinate
    system as everything else. If OCR isn't installed the page comes back empty
    rather than failing.
    """
    pages: list[PageText] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            ocr_used = False
            text, words = _extract_words(page)
            if not words:
                ocr_text, ocr_w = _ocr_words(page)   # scanned page — try OCR
                if ocr_w:
                    text, words, ocr_used = ocr_text, ocr_w, True
            if not text:
                text = page.get_text()               # last resort
            pages.append(
                PageText(page_number=i + 1, text=text, words=words, ocr=ocr_used)
            )
    return pages


def find_span(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate `needle` inside `haystack`, tolerating whitespace differences.

    Used to ground a verbatim_quote back to an exact character range on its
    page (which then becomes pixel boxes). Returns None when the quote genuinely
    isn't there — that's the anti-hallucination signal.
    """
    if not needle or not needle.strip():
        return None
    i = haystack.find(needle)                 # fast path: exact match
    if i != -1:
        return (i, i + len(needle))
    # Whitespace between tokens may differ (line breaks, double spaces).
    pattern = re.compile(r"\s+".join(re.escape(tok) for tok in needle.split()))
    m = pattern.search(haystack)
    return (m.start(), m.end()) if m else None


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
