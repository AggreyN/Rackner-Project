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

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db, ensure_visible
from app.models import Analysis as AnalysisModel
from app.models import Opportunity
from app.models import SourceDocument as SourceDocumentModel
from app.models import SourceSection as SourceSectionModel
from app.models import User
from app.schemas import SourceDocument, SourceSection
from app.services import attachments, ingest

router = APIRouter(tags=["document"])

# Single-flight per opportunity: concurrent first-builds each downloaded every
# attachment (N x SAM quota for the same files — audit 2026-08-19). The loser
# serves whatever exists rather than blocking a request thread for minutes.
import threading as _threading

_builds_inflight: set[str] = set()
_builds_lock = _threading.Lock()

# opp.id -> (monotonic deadline, link count attempted). A pass that could not
# resolve every link (dead host, quota stop) keeps attachments_accounted low,
# which made EVERY subsequent read — document view, chat turn, analysis — re-run
# the full pass, re-billing every good attachment against SAM quota forever.
# Suppress whole passes for a TTL instead. Process-local and never persisted:
# the DB still says "unresolved", so retry intent survives restarts and the
# TTL window — transient blips recover, just not on every read.
_fetch_backoff: dict[str, tuple[float, int]] = {}


def _in_backoff(opp_id: str, n_links: int) -> bool:
    entry = _fetch_backoff.get(opp_id)
    if entry is None:
        return False
    deadline, seen = entry
    if time.monotonic() >= deadline:
        _fetch_backoff.pop(opp_id, None)
        return False
    return n_links <= seen  # links added since the failed pass break through


def get_or_build_document(db: Session, opp: Opportunity) -> SourceDocumentModel:
    """Return the stored SourceDocument for this opportunity, building it once.

    The document is description + every fetchable attachment (the notice's
    resourceLinks — where the real solicitation lives). Build-once, with two
    exceptions, both of which only ever GROW the document:

    1. Built before any source text existed (search caches rows without
       descriptions; the description arrives on the detail path). Once text
       exists, an empty document is rebuilt — nothing can have verified
       against zero sections.
    2. Built with fewer attachments than the notice advertises (a download
       429'd mid-build, or links arrived after the first build). When a later
       request fetches strictly MORE attachments than the stored build has,
       the document is rebuilt — and the opportunity's stored analyses are
       deleted with it. Their citations were verified against the old text;
       a grounding document must never change underneath a stored citation.
       They regenerate against the fuller document on next view.

    If fetching yields nothing new (quota dead, links broken), the stored
    document is returned untouched — no thrash, no invalidation. One bounded
    exception to grow-only: a late-arriving description rebuilds even when
    the quota is dead, which can temporarily shrink attachment content to
    description-only; `attachments_accounted` stays low, so the next
    good-quota read regrows it, with analyses correctly invalidated both
    times.
    """
    doc = db.scalar(
        select(SourceDocumentModel).where(
            SourceDocumentModel.opportunity_id == opp.id
        )
    )

    links = list(opp.resource_links or [])[: config.SAM_MAX_ATTACHMENTS]
    description = (opp.description or "").strip()

    if doc is not None:
        needs_description = bool(description) and not doc.has_description
        wants_more = len(links) > (doc.attachments_accounted or 0)
        if not needs_description and not wants_more:
            return doc  # the common case: zero fetching, zero SAM calls
        if not needs_description and _in_backoff(opp.id, len(links)):
            return doc  # a recent pass already failed on these links

    with _builds_lock:
        if opp.id in _builds_inflight:
            # Another request is mid-build (downloads can take a while). Serve
            # the current state; the winner's build lands shortly. With no
            # stored doc yet, return a TRANSIENT empty one — persisting a
            # placeholder raced the winner's insert and could discard its
            # paid-for downloads (audit-2 finding).
            if doc is not None:
                return doc
            return SourceDocumentModel(
                opportunity_id=opp.id, label="", attachments_ingested=0,
                attachments_accounted=0, has_description=False,
            )
        _builds_inflight.add(opp.id)
        blobs = None  # sentinel: we own the build
    if blobs is None:
        try:
            blobs, exhausted = attachments.fetch_all(links)
        finally:
            with _builds_lock:
                _builds_inflight.discard(opp.id)
        if exhausted:
            _fetch_backoff.pop(opp.id, None)
        else:
            _fetch_backoff[opp.id] = (
                time.monotonic() + config.ATTACHMENT_RETRY_BACKOFF_MINUTES * 60,
                len(links),
            )
    # exhausted: every link resolved (fetched, or dead in a way retrying won't
    # fix) — record them all so no future read re-attempts them. A quota-stop
    # accounts only the successes, leaving the rest for a fresh-quota day.
    accounted = len(links) if exhausted else len(blobs)

    # Parse once, here: "grew" must mean MORE GROUNDING TEXT, not more bytes.
    # Comparing blob counts let a text-less attachment trigger a rebuild with
    # byte-identical sections that deleted every user's analyses for nothing
    # (audit 2026-08-19).
    attachment_texts: list[str] = []
    for blob in blobs:
        try:
            text = ingest.load_text(blob)
        except Exception:
            text = ""
        if text.strip():
            attachment_texts.append(text)

    if doc is not None:
        needs_description = bool(description) and not doc.has_description
        grew = len(attachment_texts) > (doc.attachments_ingested or 0)
        if doc.sections and not grew and not needs_description:
            # Nothing new to build — but remember what got resolved, so dead
            # links stop being retried on every read.
            if accounted > (doc.attachments_accounted or 0):
                doc.attachments_accounted = accounted
                db.commit()
            return doc
        if not doc.sections and not blobs and not description:
            # Still nothing to build from — but an exhausted pass must be
            # recorded even on an empty doc, or permanently-dead links get
            # re-downloaded on every read of a description-less opportunity.
            if accounted > (doc.attachments_accounted or 0):
                doc.attachments_accounted = accounted
                db.commit()
            return doc
        if doc.sections:
            # The document is about to change: stored citations were verified
            # against the old build, so the analyses carrying them go too.
            db.query(AnalysisModel).filter(
                AnalysisModel.opportunity_id == opp.id
            ).delete(synchronize_session=False)
        db.delete(doc)
        db.flush()

    payload = ingest.build_source_document(opp, attachment_texts=attachment_texts)
    # The INSERT executes at flush, not commit — the unique-index violation
    # from a concurrent builder raises there, so the whole insert lives
    # inside the try.
    try:
        doc = SourceDocumentModel(
            opportunity_id=opp.id,
            label=payload["label"],
            attachments_ingested=len(attachment_texts),
            attachments_accounted=accounted,
            has_description=bool(description),
        )
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
    except IntegrityError:
        # A concurrent builder (detail-view prewarm vs a document GET) won the
        # unique-index race. Their document is as good as ours — serve it.
        # Rolling back also undoes our analyses-delete, which was never valid
        # for the winner's build.
        db.rollback()
        return db.scalar(
            select(SourceDocumentModel).where(
                SourceDocumentModel.opportunity_id == opp.id
            )
        )
    db.refresh(doc)
    return doc


def to_schema(doc: SourceDocumentModel, opp: Opportunity) -> SourceDocument:
    return SourceDocument(
        opportunity_id=doc.opportunity_id,
        label=doc.label or "",
        sections=[
            SourceSection(ref=s.ref, heading=s.heading, text=s.text, page=s.page)
            for s in doc.sections
        ],
        attachments_ingested=doc.attachments_ingested or 0,
        attachments_accounted=doc.attachments_accounted or 0,
        attachments_expected=min(
            len(opp.resource_links or []), config.SAM_MAX_ATTACHMENTS
        ),
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
    ensure_visible(opp, user)
    return to_schema(get_or_build_document(db, opp), opp)
