"""Clause segmentation — splits page text into FAR/DFARS clause chunks.

Sits between Aggrey's extract_pdf.py (unchanged) and Kaliza's extractor
(unchanged). Each chunk keeps its page + character offsets so citations
survive all the way to the frontend highlight.
"""

import re
from dataclasses import dataclass

# Matches "52.204-21", "252.204-7012", with optional "FAR"/"DFARS" prefix.
CLAUSE_REF = re.compile(r"\b(?:FAR\s+|DFARS\s+)?(52\.\d{3}-\d{1,3}|252\.\d{3}-\d{4})\b")


@dataclass
class Chunk:
    clause_ref: str | None   # None for narrative sections between clauses
    text: str
    page: int
    char_start: int
    char_end: int


def segment_pages(pages: list) -> list[Chunk]:
    """Take extract_pdf's Page objects (page_number, text) → clause chunks.

    Strategy v1: within each page, split at clause-reference boundaries.
    Text before the first reference becomes a narrative chunk. Cross-page
    clause stitching is a known v2 item (tracked for Week 3).
    """
    chunks: list[Chunk] = []
    for p in pages:
        text = p.text or ""
        hits = list(CLAUSE_REF.finditer(text))
        if not hits:
            if text.strip():
                chunks.append(Chunk(None, text, p.page_number, 0, len(text)))
            continue

        if hits[0].start() > 0 and text[: hits[0].start()].strip():
            chunks.append(Chunk(None, text[: hits[0].start()], p.page_number, 0, hits[0].start()))

        for i, m in enumerate(hits):
            end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
            chunks.append(
                Chunk(
                    clause_ref=m.group(1),
                    text=text[m.start(): end],
                    page=p.page_number,
                    char_start=m.start(),
                    char_end=end,
                )
            )
    return chunks
