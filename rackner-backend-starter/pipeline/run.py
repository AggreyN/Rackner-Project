"""End-to-end pipeline: PDF → pages → clause chunks → obligations → Postgres.

Composes the three owners' modules without modifying any of them:
    Aggrey's  ingestion.extract_pdf.extract_pages
    the new   ingestion.segment.segment_pages
    Kaliza's  extractor (via extraction.adapter)

Also runs verification: each verbatim_quote is string-matched back to the
source text; quotes we can't find are stored but flagged verified=False.
"""

from sqlalchemy.orm import Session

from ingestion.extract_pdf import extract_pages
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
            )
            session.add(clause)
            session.flush()  # get clause.id

            for raw in extract_obligations(chunk.text):
                quote = raw.get("verbatim_quote") or ""
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
                        confidence=raw.get("confidence"),
                        # Anti-hallucination check: quote must exist in source.
                        verified=bool(quote) and _normalize(quote) in norm_full,
                    )
                )

        doc.status = "ready"
    except Exception:
        doc.status = "failed"
        raise
    finally:
        session.commit()
