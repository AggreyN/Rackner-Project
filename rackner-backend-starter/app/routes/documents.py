"""The grounding document.

    GET /opportunities/{id}/document -> SourceDocument

Serves the persisted sections byte-for-byte. This endpoint and the analysis
path read the same rows, which is what makes the UI's
`section.text.indexOf(quote)` succeed for every verified obligation.

Building is idempotent: the first request for an opportunity parses and
persists; later requests replay the stored rows. Never re-parse on read — a
re-parse could produce different text than the quotes were verified against.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.models import Opportunity
from app.models import SourceDocument as SourceDocumentModel
from app.models import SourceSection as SourceSectionModel
from app.models import User
from app.schemas import SourceDocument, SourceSection
from app.services import ingest

router = APIRouter(tags=["document"])


def get_or_build_document(db: Session, opp: Opportunity) -> SourceDocumentModel:
    """Return the stored SourceDocument for this opportunity, building it once.

    One exception to build-once: a document built when the opportunity had no
    source text yet. Search caches opportunities WITHOUT descriptions (the
    description is a second, slow SAM call made on the detail path), so hitting
    /document, /chat or /analysis before the detail view builds an empty
    document. Once real text exists, an empty document is rebuilt — safe,
    because nothing can have verified against zero sections, so no quote's
    grounding text changes out from under it.
    """
    doc = db.scalar(
        select(SourceDocumentModel).where(
            SourceDocumentModel.opportunity_id == opp.id
        )
    )
    if doc is not None:
        if doc.sections or not (opp.description or "").strip():
            return doc
        # Built before any source text existed; rebuild now that it does.
        db.delete(doc)
        db.flush()

    payload = ingest.build_source_document(opp)
    doc = SourceDocumentModel(opportunity_id=opp.id, label=payload["label"])
    db.add(doc)
    db.flush()  # assign doc.id before attaching sections

    for position, sec in enumerate(payload["sections"]):
        db.add(
            SourceSectionModel(
                document_id=doc.id,
                ref=sec["ref"],
                heading=sec["heading"],
                text=sec["text"],  # canonical — stored exactly as sliced
                page=sec["page"],
                position=position,
            )
        )
    db.commit()
    db.refresh(doc)
    return doc


def to_schema(doc: SourceDocumentModel) -> SourceDocument:
    return SourceDocument(
        opportunity_id=doc.opportunity_id,
        label=doc.label or "",
        sections=[
            SourceSection(ref=s.ref, heading=s.heading, text=s.text, page=s.page)
            for s in doc.sections
        ],
    )


@router.get("/opportunities/{opportunity_id}/document", response_model=SourceDocument)
def get_document(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SourceDocument:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
    return to_schema(get_or_build_document(db, opp))
