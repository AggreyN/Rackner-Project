"""Import a contract PDF that is not on SAM.gov.

    POST /opportunities/import  (multipart file) -> OpportunitySummary

The uploaded document runs the normal pipeline — full-text extraction (OCR
included), canonicalization, sectioning — and lands as a first-class
opportunity: analysis, Anvil chat, and click-to-cite all work identically to
SAM-sourced notices. The production-handoff decisions, implemented:

  * IDs: ``imp_<uuid4hex>`` — can never collide with or be mistaken for a
    SAM notice id.
  * Visibility: private to the uploader (opportunities.owner_id); imported
    rows never appear in shared lists and 404 for anyone else.
  * Deduplication: identical bytes re-uploaded by the same user return the
    EXISTING opportunity instead of a confusing duplicate (sha256).
  * Metadata: extracted from the opening pages by the model when available
    (title, agency, NAICS, set-aside, close date), with filename-derived
    fallbacks — an import never fails because metadata extraction did.

The grounding document is built HERE, at import time, from the full text.
The row's `description` holds only a card-sized summary; the document is the
source of truth and is never rebuilt (no resource links, description marked
present, all attachments accounted).
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.llm import gateway
from app.models import Opportunity, User
from app.routes.documents import get_or_build_document
from app.routes.opportunities import _apply_fit, _lifecycle, _to_summary
from app.schemas import OpportunitySummary
from app.services import ingest, storage

log = logging.getLogger(__name__)

router = APIRouter(tags=["import"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB, same as the lifecycle upload
CARD_SUMMARY_CHARS = 1200


def _title_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename or "imported-document").stem
    return stem.replace("_", " ").replace("-", " ").strip()[:200] or "Imported document"


@router.post("/opportunities/import", response_model=OpportunitySummary)
async def import_opportunity(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> OpportunitySummary:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    filename = file.filename or "imported-document.pdf"
    text = ingest.load_text(data, filename)
    if not text.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No text could be read from that file. If it is a scanned PDF, "
            "upload a text-based version.",
        )

    # Same bytes, same uploader -> the existing record, not a duplicate.
    content_hash = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Opportunity).where(
            Opportunity.owner_id == user.id,
            Opportunity.import_hash == content_hash,
        )
    )
    if existing is not None:
        summary = _to_summary(existing)
        _apply_fit(db, user, [summary], _lifecycle(db, user))
        return OpportunitySummary(**{k: v for k, v in summary.items() if not k.startswith("_")})

    meta = gateway.extract_import_metadata(text)
    opp_id = f"imp_{uuid.uuid4().hex}"

    storage.put(data, filename=filename, prefix="imported")

    close_date = None
    raw_close = meta.get("close_date")
    if raw_close:
        try:
            close_date = datetime.date.fromisoformat(raw_close[:10])
        except ValueError:
            close_date = None

    row = Opportunity(
        id=opp_id,
        title=meta.get("title") or _title_from_filename(filename),
        agency=meta.get("agency") or "Imported document",
        solicitation_number=meta.get("solicitation_number"),
        naics=meta.get("naics"),
        set_aside=meta.get("set_aside"),
        kind="solicitation",
        # Card-sized summary only — the FULL text becomes the grounding
        # document below and is the source of truth from here on.
        description=text[:CARD_SUMMARY_CHARS],
        close_date=close_date,
        owner_id=user.id,
        import_hash=content_hash,
        description_fetched_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Build the grounding document NOW from the full text, through the same
    # sectioning pipeline as SAM packages. get_or_build_document would only
    # see the card summary, so this build must happen here.
    payload = ingest.build_source_document(
        {"id": opp_id, "description": text, "title": row.title,
         "solicitation_number": row.solicitation_number},
    )
    from app.models import SourceDocument as SourceDocumentModel
    from app.models import SourceSection as SourceSectionModel

    doc = SourceDocumentModel(
        opportunity_id=opp_id,
        label=payload["label"],
        attachments_ingested=0,
        attachments_accounted=0,
        has_description=True,
    )
    db.add(doc)
    db.flush()
    for position, sec in enumerate(payload["sections"]):
        db.add(
            SourceSectionModel(
                document_id=doc.id,
                ref=sec["ref"],
                heading=sec["heading"],
                text=sec["text"],
                page=sec["page"],
                position=position,
            )
        )
    db.commit()

    log.info(
        "imported opportunity %s (%d chars, %d sections) for user %d",
        opp_id,
        len(text),
        len(payload["sections"]),
        user.id,
    )

    summary = _to_summary(row)
    _apply_fit(db, user, [summary], _lifecycle(db, user))
    return OpportunitySummary(**{k: v for k, v in summary.items() if not k.startswith("_")})
