"""Solicitation → SourceDocument. The grounding layer.

THE INVARIANT THIS FILE EXISTS TO PROTECT
-----------------------------------------
`SourceSection.text` is the canonical string. Everything downstream depends on
it being byte-exact:

  * the LLM is shown this exact string,
  * `verified` is computed by substring test against this exact string,
  * `GET /document` serves this exact string,
  * the UI highlights with `section.text.indexOf(quote)`.

So sectioning is done by SLICING (`raw[start:end]`) and never by rebuilding
text from parts. No whitespace collapsing, no de-hyphenation, no `.strip()` that
isn't reflected in the recorded offsets. If you add a cleanup step here, do it
BEFORE sectioning, to the whole raw string, once — never between "what we match
against" and "what we serve".

Text sources, in order: the cached opportunity `description`, then any attached
PDFs (pypdf). Scanned/image-only PDFs come back empty — see the Textract hook.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from app import config

log = logging.getLogger(__name__)

# --- canonicalization --------------------------------------------------------
# PDF extraction emits characters the model will not reproduce when asked to
# quote verbatim: curly quotes, en/em dashes, non-breaking spaces, ligatures,
# soft hyphens left over from justified text. Those cause a quote that is
# correct in substance to fail an exact-substring test.
#
# We fix that ONCE, HERE, at the boundary where text enters the system — before
# it is sectioned, stored, matched against, or served. That ordering is the
# whole safety argument: the canonical string IS the served string, so
# canonicalizing cannot desynchronize "what we match" from "what we serve".
#
# Doing this later — between verification and `GET /document` — is precisely
# the bug this module's docstring warns about. Don't.

_CHAR_FIXES = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",  # single quotes
    "“": '"', "”": '"', "„": '"', "‟": '"',  # double quotes
    "‐": "-", "‑": "-", "‒": "-", "–": "-",  # hyphens/dashes
    "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ",  # hard spaces
    "­": "",                                                # soft hyphen
    "​": "", "‌": "", "‍": "", "﻿": "",      # zero-width
}
_CHAR_FIXES_TABLE = str.maketrans(_CHAR_FIXES)


def canonicalize(text: str) -> str:
    """The one normalization pass, applied where text enters the system.

    NFKC folds ligatures and compatibility forms; the table above unifies the
    punctuation PDF extractors vary on. Line endings become "\\n". Idempotent:
    canonicalize(canonicalize(x)) == canonicalize(x).

    Whitespace is NOT collapsed — that would change offsets and lose the
    document's shape. Whitespace drift is handled at match time by
    verify.realign_quote(), which snaps a quote back onto this exact string.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text)
    return text.translate(_CHAR_FIXES_TABLE)


# Headings we treat as section boundaries, matched on the ORIGINAL string so
# every span index stays meaningful:
#   "SECTION C — DESCRIPTION"      → ref "C"
#   "C.3.1 Deliverables"           → ref "C.3.1"
#   "252.204-7012 Safeguarding"    → ref "252.204-7012"  (FAR/DFARS clause)
#   "§L.2 Instructions"            → ref "L.2"           ("§" stripped per v2)
_HEADING_RE = re.compile(
    r"""^[ \t]*(?:
          SECTION[ \t]+(?P<sec>[A-Z])\b
        | §[ \t]*(?P<para>[A-Z]\.[0-9][0-9.]*)
        | (?P<clause>\d{2,3}\.\d{3}-\d+)
        | (?P<dotted>[A-Z]\.[0-9][0-9.]*)
      )
      [ \t]*(?P<heading>[^\n]*)$""",
    re.MULTILINE | re.VERBOSE,
)

_PAGE_BREAK = "\f"


def _page_for_offset(raw: str, offset: int) -> int:
    """1-based page number, counting form feeds inserted by the PDF reader."""
    return raw.count(_PAGE_BREAK, 0, offset) + 1


def _split_by_page(raw: str) -> list[dict]:
    """Fallback when no clause headings are found: one section per page.

    Measured on real solicitations, some documents expose no matchable heading
    structure at all — a 638-page sample collapsed to a single 1.24M-character
    section. That is unusable: it exceeds the model's context in one call and
    makes `citation.section` meaningless because every quote cites the same
    section.

    Page boundaries always exist (the PDF reader inserts form feeds), so they
    give a bounded, honest unit of citation. Refs are "p1", "p2", ... which are
    clearly not clause ids.

    Slices only — concatenating the results reproduces `raw` exactly, form feeds
    included.
    """
    sections: list[dict] = []
    start = 0
    page = 1
    while start < len(raw):
        nxt = raw.find(_PAGE_BREAK, start)
        end = len(raw) if nxt == -1 else nxt + 1  # keep the \f with its page
        chunk = raw[start:end]
        if chunk.strip():
            sections.append(
                {"ref": f"p{page}", "heading": "", "text": chunk, "page": page}
            )
        elif sections:
            # Blank page: append to the previous section so no character is lost.
            sections[-1]["text"] += chunk
        elif chunk:
            sections.append({"ref": f"p{page}", "heading": "", "text": chunk, "page": page})
        start = end
        page += 1
    return sections


def split_sections(raw: str) -> list[dict]:
    """Split raw text into sections without altering a single character.

    Returns dicts of {ref, heading, text, page}. `text` is always exactly
    `raw[start:end]` for some span, so `raw.find(section['text'])` succeeds and
    any quote found inside a section is also found in `raw`.
    """
    if not raw:
        return []

    matches = list(_HEADING_RE.finditer(raw))
    if not matches:
        return _split_by_page(raw)

    sections: list[dict] = []

    # Anything before the first heading is still quotable; keep it.
    if matches[0].start() > 0:
        preamble = raw[: matches[0].start()]
        if preamble.strip():
            sections.append(
                {"ref": "0", "heading": "Preamble", "text": preamble, "page": 1}
            )

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        ref = m.group("sec") or m.group("para") or m.group("clause") or m.group("dotted")
        sections.append(
            {
                # SCHEMA_v2: refs are stored WITHOUT the "§" prefix.
                "ref": (ref or "").lstrip("§").strip(),
                "heading": (m.group("heading") or "").strip(),
                # Verbatim slice — the whole point of this module.
                "text": raw[start:end],
                "page": _page_for_offset(raw, start),
            }
        )
    return sections


def pdf_to_text(data: bytes) -> str:
    """Extract text from a PDF, one form feed between pages.

    Digital pages come from pypdf. Pages with no text layer degrade to "" —
    unless OCR_MODE=textract, in which case ONLY those pages are rendered
    locally (PyMuPDF) and OCR'd via Amazon Textract's synchronous
    DetectDocumentText. Hybrid on purpose: digital pages keep their byte-exact
    pypdf text; OCR touches nothing it doesn't have to.

    OCR failures degrade to the pypdf result rather than raising — a Textract
    outage must not take ingestion down with it.
    """
    pages = _pypdf_page_texts(data)

    if config.OCR_MODE == "textract":
        pages = _ocr_textless_pages(data, pages)

    if not pages:
        return ""
    # Canonicalized here, at the boundary — everything downstream (sectioning,
    # storage, verification, GET /document) sees this one string.
    return canonicalize(_PAGE_BREAK.join(pages))


def _pypdf_page_texts(data: bytes) -> list[str]:
    """Per-page text via pypdf. [] when the bytes aren't a readable PDF."""
    try:
        import io

        from pypdf import PdfReader
    except ImportError:  # pypdf not installed — degrade, don't crash
        return []

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return []

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


# A page with fewer characters than this has no real text layer. (The scanned
# samples measure 0 and 1 chars for whole documents; a genuine page of a
# solicitation is thousands.)
_OCR_MIN_CHARS = 20

# Render scale for OCR: 72dpi * 2 = 144dpi — Textract's sweet spot without
# blowing the sync API's 5MB-per-image limit on letter-size pages.
_OCR_ZOOM = 2.0


def _render_page_png(data: bytes, index: int) -> bytes | None:
    """Rasterize one PDF page to PNG bytes with PyMuPDF. None on any failure."""
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            page = doc[index]
            pix = page.get_pixmap(matrix=fitz.Matrix(_OCR_ZOOM, _OCR_ZOOM))
            return pix.tobytes("png")
    except Exception:
        log.warning("could not rasterize page %d for OCR", index, exc_info=True)
        return None


def _textract_lines(png: bytes) -> str | None:
    """One synchronous DetectDocumentText call. None on any failure.

    LINE blocks joined with newlines — WORD blocks would lose the layout the
    section splitter keys on.
    """
    try:
        import boto3

        client = boto3.client("textract", region_name=config.AWS_REGION)
        response = client.detect_document_text(Document={"Bytes": png})
    except Exception:
        log.warning("Textract OCR call failed", exc_info=True)
        return None
    return "\n".join(
        block["Text"]
        for block in response.get("Blocks", [])
        if block.get("BlockType") == "LINE" and block.get("Text")
    )


def _page_count(data: bytes) -> int:
    """Page count via PyMuPDF, for PDFs pypdf couldn't read at all."""
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            return doc.page_count
    except Exception:
        return 0


def _ocr_textless_pages(data: bytes, pages: list[str]) -> list[str]:
    """OCR exactly the pages that have no usable text layer.

    Hybrid: a mixed document (digital pages + scanned exhibits) keeps its
    byte-exact pypdf text everywhere pypdf worked. Every failure path returns
    what we already had.
    """
    if not pages:
        # pypdf couldn't even open it; PyMuPDF often still can.
        count = _page_count(data)
        if count == 0:
            return pages
        pages = [""] * count

    needs_ocr = [i for i, text in enumerate(pages) if len(text.strip()) < _OCR_MIN_CHARS]
    if not needs_ocr:
        return pages

    ocred = 0
    for index in needs_ocr:
        png = _render_page_png(data, index)
        if png is None:
            continue
        text = _textract_lines(png)
        if text:
            pages[index] = text
            ocred += 1

    log.info(
        "textract OCR: %d/%d text-less pages recovered",
        ocred,
        len(needs_ocr),
        extra={"pages_ocred": ocred, "pages_needing_ocr": len(needs_ocr)},
    )
    return pages


def load_text(data: bytes, filename: str = "") -> str:
    """Bytes → canonical text. PDF if it looks like one, else decoded as UTF-8."""
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        return pdf_to_text(data)
    return canonicalize(data.decode("utf-8", errors="replace"))


def build_source_document(opportunity, attachments: list[bytes] | None = None) -> dict:
    """Assemble the SourceDocument payload for one opportunity.

    `opportunity` may be an ORM row or a dict. Attachment bytes, when supplied,
    are appended after the cached description.
    """
    if isinstance(opportunity, dict):
        opp_id = opportunity.get("id", "")
        description = opportunity.get("description", "") or ""
        sol_no = opportunity.get("solicitation_number") or ""
        title = opportunity.get("title", "") or ""
    else:
        opp_id = getattr(opportunity, "id", "")
        description = getattr(opportunity, "description", "") or ""
        sol_no = getattr(opportunity, "solicitation_number", "") or ""
        title = getattr(opportunity, "title", "") or ""

    # The cached description comes from SAM.gov, not from load_text(), so it
    # needs the same canonicalization the attachments already got.
    description = canonicalize(description)
    parts = [description] if description.strip() else []
    for blob in attachments or []:
        text = load_text(blob)
        if text.strip():
            parts.append(text)

    # Join once, up front, then section the joined string. Sectioning after the
    # join is what keeps every section an exact slice of what we serve.
    raw = "\n\n".join(parts)

    label = f"Source solicitation · {sol_no}" if sol_no else (title or "Source document")
    return {
        "opportunity_id": opp_id,
        "label": label,
        "sections": split_sections(raw),
    }
