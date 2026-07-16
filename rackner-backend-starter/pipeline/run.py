"""End-to-end pipeline: PDF → pages → clause chunks → obligations → database.

Composes the three owners' modules without modifying any of them:
    Aggrey's  ingestion.extract_pdf.extract_pages
    Aggrey's  ingestion.segment.segment_pages
    Kaliza's  extractor (via extraction.adapter)

Also runs verification: each verbatim_quote is located in its source page, which
both proves the quote is real (anti-hallucination) and yields the exact pixel
boxes the frontend highlights. Quotes we can't find anywhere are still stored,
flagged verified=False.
"""

from sqlalchemy.orm import Session

from ingestion.extract_pdf import extract_pages, boxes_for_span, find_span
from ingestion.segment import segment_pages
from extraction.adapter import extract_obligations
from core.pii import scan_text
from db.models import Document, Clause, Obligation


def _normalize(s: str) -> str:
    return " ".join((s or "").split()).lower()


def process_document(session: Session, doc: Document) -> None:
    """Run the full pipeline for one uploaded document. Sets doc.status."""
    try:
        pages = extract_pages(doc.file_path)
        doc.num_pages = len(pages)
        pages_by_number = {p.page_number: p for p in pages}

        full_text = "\n".join(p.text for p in pages)
        norm_full = _normalize(full_text)

        # Record PII kinds/counts on the document (masked; no raw values stored).
        findings = scan_text(full_text)
        doc.pii_findings = {f.kind: f.count for f in findings} or None

        for chunk in segment_pages(pages):
            clause = Clause(
                document_id=doc.id,
                clause_ref=chunk.clause_ref,
                text=chunk.text,
                page=chunk.page,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                boxes=[list(b) for b in chunk.boxes] or None,
            )
            session.add(clause)
            session.flush()  # get clause.id

            page = pages_by_number.get(chunk.page)

            for raw in extract_obligations(chunk.text):
                quote = raw.get("verbatim_quote") or ""

                # Ground the quote: find its exact span on the page, then turn
                # that span into pixel boxes. Finding it *is* the verification.
                span = find_span(page.text, quote) if (page and quote) else None
                qboxes = boxes_for_span(page, *span) if (span and page) else []
                # Fall back to the whole-document check so a quote that straddles
                # a page break still verifies (it just won't carry boxes).
                verified = bool(span) or (bool(quote) and _normalize(quote) in norm_full)

                session.add(
                    Obligation(
                        document_id=doc.id,
                        source_clause_id=clause.id,
                        plain_english_text=raw.get("plain_english_text", ""),
                        obligation_type=raw.get("obligation_type"),
                        trigger_or_deadline=raw.get("trigger_or_deadline"),
                        responsible_party=raw.get("responsible_party"),
                        roles=raw.get("roles"),
                        category=raw.get("category"),
                        time_bucket=raw.get("time_bucket"),
                        verbatim_quote=quote,
                        page=chunk.page,
                        quote_char_start=span[0] if span else None,
                        quote_char_end=span[1] if span else None,
                        quote_boxes=[list(b) for b in qboxes] or None,
                        confidence=raw.get("confidence"),
                        verified=verified,
                    )
                )

        doc.status = "ready"
    except Exception:
        doc.status = "failed"
        raise
    finally:
        session.commit()
