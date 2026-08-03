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

import re

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
        # No recognizable structure — one section holding the whole string.
        return [{"ref": "1", "heading": "", "text": raw, "page": 1}]

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
    """Extract text from a digital PDF, one form feed between pages.

    Returns "" for scanned/image-only PDFs (pypdf finds no text layer) rather
    than raising — the caller falls back to other sources.

    TODO(week4, optional): if a dry run hits a scanned solicitation, add an
    Amazon Textract fallback here. Keep it behind a config flag and make it
    return the same plain string, so nothing downstream changes.
    """
    try:
        import io

        from pypdf import PdfReader
    except ImportError:  # pypdf not installed — degrade, don't crash
        return ""

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return ""

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return _PAGE_BREAK.join(pages)


def load_text(data: bytes, filename: str = "") -> str:
    """Bytes → text. PDF if it looks like one, else decoded as UTF-8."""
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        return pdf_to_text(data)
    return data.decode("utf-8", errors="replace")


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
