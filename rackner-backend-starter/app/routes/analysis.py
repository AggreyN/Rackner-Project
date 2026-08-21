"""Analysis — generate-on-GET, cached.

    GET /opportunities/{id}/analysis -> Analysis

Remy's frontend only ever GETs this; there is no POST-to-generate. So a miss
generates inline and persists, and every later request is a cache hit.

LATENCY — FLAGGED FOR REMY (SCHEMA_v2.md, open question 3)
----------------------------------------------------------
With LLM_MODE=bedrock over a 100-page solicitation this can exceed 30s, and the
client sets no timeout. Two options were on the table:
  (a) keep GET synchronous and make sure it usually hits cache  <- implemented
  (b) 202 + poll                                                <- contract change

`ensure_analysis()` is the seam for (b): it is the whole generate-and-persist
step, callable from a background task or a warm-up job without touching the
route. Switching to (b) means returning {"status": "pending"} here and calling
ensure_analysis() out of band — no other module changes.

Also kept: POST /llm/extract and GET /llm/status, which Kaliza uses to test the
extractor in isolation. The UI does not call them.
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db, ensure_visible
from app.llm import gateway
from app.models import Analysis as AnalysisModel
from app.models import LifecycleProfile as LifecycleProfileModel
from app.models import Opportunity, User
from app.models import SourceDocument as SourceDocumentModel
from app.routes.documents import get_or_build_document
from app.schemas import Analysis, Obligation

log = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

# --------------------------------------------------------------------------- #
# In-flight guard.
#
# One (user, opportunity) analysis may be generating at a time — whether the
# trigger was a background pre-warm or a direct GET. Without this, a user who
# opens the analysis tab while the warm is mid-flight buys the same 30s+
# Bedrock call twice. Process-local by design: with several ECS tasks the
# worst case is one duplicate call per task, which is an acceptable cost for
# not needing a distributed lock.
# --------------------------------------------------------------------------- #
_inflight: set[tuple[int, str]] = set()
_inflight_lock = threading.Lock()


def _acquire(user_id: int, opportunity_id: str) -> bool:
    with _inflight_lock:
        key = (user_id, opportunity_id)
        if key in _inflight:
            return False
        _inflight.add(key)
        return True


def _release(user_id: int, opportunity_id: str) -> None:
    with _inflight_lock:
        _inflight.discard((user_id, opportunity_id))


def _is_inflight(user_id: int, opportunity_id: str) -> bool:
    with _inflight_lock:
        return (user_id, opportunity_id) in _inflight


class ExtractRequest(BaseModel):
    chunk_text: str


def _lifecycle_dict(db: Session, user: User) -> dict:
    """The user's saved plan as the gateway expects it (v2 key names)."""
    row = db.scalar(
        select(LifecycleProfileModel)
        .where(LifecycleProfileModel.user_id == user.id)
        .order_by(LifecycleProfileModel.updated_at.desc())
    )
    if row is None:
        return {}
    return {
        "capabilities": row.capabilities or [],
        "naics_codes": row.naics_codes or [],
        "target_agencies": row.target_agencies or [],
        "set_asides": row.set_aside_status or [],
        "past_performance": row.past_performance or [],
        "contract_vehicles": row.contract_vehicles or [],
        "size_min": float(row.size_min) if row.size_min is not None else None,
        "size_max": float(row.size_max) if row.size_max is not None else None,
    }


def _opportunity_dict(opp: Opportunity) -> dict:
    return {
        "id": opp.id,
        "title": opp.title,
        "agency": opp.agency,
        "office": opp.office,
        "naics": opp.naics,
        "set_aside": opp.set_aside,
        "kind": opp.kind,
        "description": opp.description,
        "close_date": opp.close_date.isoformat() if opp.close_date else None,
        "est_value": opp.est_value,
        "incumbent": opp.incumbent,
    }


def _to_schema(row: AnalysisModel) -> Analysis:
    return Analysis(
        opportunity_id=row.opportunity_id,
        # Clamp on read too: rows persisted before the write-side clamp must
        # serve, not 500 forever.
        score=min(100.0, max(0.0, row.score)),
        band=row.band,
        verdict=row.verdict or "",
        factors=row.factors or [],
        obligations=row.obligations or [],
    )


def _cached_analysis(
    db: Session, opportunity_id: str, user_id: int
) -> AnalysisModel | None:
    return db.scalar(
        select(AnalysisModel)
        .where(
            AnalysisModel.opportunity_id == opportunity_id,
            AnalysisModel.user_id == user_id,
        )
        .order_by(AnalysisModel.generated_at.desc())
    )


def ensure_analysis(db: Session, opp: Opportunity, user: User) -> AnalysisModel:
    """Return this user's analysis for the opportunity, generating it on a miss.

    This is the (b)-option seam: safe to call from a background task or warm-up
    job. Generation reads the persisted SourceDocument sections, so obligations
    are verified against the same text `GET /document` serves.
    """
    row = _cached_analysis(db, opp.id, user.id)
    if row is not None:
        return row

    if not _acquire(user.id, opp.id):
        # Someone else (a pre-warm, or another request) is generating this
        # exact analysis. Wait for their row instead of paying for the same
        # model call twice.
        row = _wait_for_inflight(db, opp.id, user.id, timeout_s=45.0)
        if row is not None:
            return row
        if not _acquire(user.id, opp.id):
            # Still generating after the wait. The old fallback started a
            # duplicate multi-minute model run here — under a big document,
            # stacked retries wedged the prod task for ~10 minutes (measured
            # 2026-08-11). Tell the client to come back for the cached row
            # instead; the holder's run is still making progress.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "This analysis is still being generated. Retry in a moment.",
                headers={"Retry-After": "20"},
            )

    try:
        # Re-check inside the guard: the previous holder may have landed a row
        # between our cache miss and our acquire.
        row = _cached_analysis(db, opp.id, user.id)
        if row is not None:
            return row
        return _generate_and_store(db, opp, user)
    finally:
        _release(user.id, opp.id)


def _generate_and_store(db: Session, opp: Opportunity, user: User) -> AnalysisModel:
    doc = get_or_build_document(db, opp)
    # Materialize everything the model needs as plain data, then COMMIT to
    # end the transaction and release this session's pooled connection —
    # generation runs for minutes, and ~15 concurrently held connections
    # (pool_size+overflow) meant sitewide 500s (audit 2026-08-19).
    sections = [
        {"ref": sec.ref, "page": sec.page, "text": sec.text} for sec in doc.sections
    ]
    had_sections = bool(sections)
    # Identity of the build this analysis grounds against. id alone is not
    # enough — SQLite reuses rowids after delete+insert — but a rebuilt row
    # always carries a new created_at.
    build_identity = (doc.id, doc.created_at)
    opp_dict = _opportunity_dict(opp)
    profile_dict = _lifecycle_dict(db, user)
    # Identity of the PLAN this analysis scores against — a re-upload or
    # removal mid-generation must make the result transient, or a
    # stale-profile verdict survives the wipe (audit-2 finding).
    plan_marker = db.scalar(
        select(LifecycleProfileModel.updated_at).where(
            LifecycleProfileModel.user_id == user.id
        )
    )
    db.commit()  # release the connection for the duration of the model call
    result = gateway.analyze(opp_dict, profile_dict, sections)

    row = AnalysisModel(
        opportunity_id=opp.id,
        user_id=user.id,
        score=result["score"],
        band=result["band"],
        verdict=result["verdict"],
        factors=result["factors"],
        obligations=result["obligations"],
    )
    # Persist (= cache) only analyses that had source text to ground in. An
    # analysis generated against zero sections has no obligations by
    # construction; caching it would freeze that empty result even after the
    # description arrives and the document rebuilds. Returned transient, it is
    # regenerated on each request until grounding exists, then cached.
    if had_sections:
        # The model call took seconds; the grounding document may have been
        # rebuilt underneath us in that window (attachments arriving on a
        # concurrent request replace the document row). Persisting an analysis
        # generated against the OLD build would break the invariant that
        # grounding text never changes under a stored citation — so persist
        # only if the CURRENT build (fresh transaction) is still the one we
        # generated against.
        db.commit()  # end our read transaction so the re-check sees current state
        current = db.scalar(
            select(SourceDocumentModel).where(
                SourceDocumentModel.opportunity_id == opp.id
            )
        )
        if current is None or (current.id, current.created_at) != build_identity:
            log.info(
                "analysis for %s served transient: the grounding document "
                "was rebuilt mid-generation",
                opp.id,
            )
            return row
        current_plan = db.scalar(
            select(LifecycleProfileModel.updated_at).where(
                LifecycleProfileModel.user_id == user.id
            )
        )
        if current_plan != plan_marker:
            log.info(
                "analysis for %s served transient: the lifecycle plan "
                "changed mid-generation",
                opp.id,
            )
            return row
        try:
            db.add(row)
            db.commit()
        except IntegrityError:
            # A concurrent generation persisted first (unique index on
            # opportunity+user). Serve theirs — same document, same inputs.
            db.rollback()
            return _cached_analysis(db, opp.id, user.id) or row
        db.refresh(row)
    return row


def warm_analysis(opportunity_id: str, user_id: int) -> None:
    """Best-effort background pre-generation (SCHEMA_v2 question 3, option (a)).

    Fired from the opportunity detail view so that by the time the user clicks
    the analysis tab, GET /analysis is a cache hit instead of a synchronous
    model call. Opens its OWN session: FastAPI tears down request dependencies
    before background tasks run, so the request's session is already closed.

    Skips silently when an analysis is cached, one is already generating, or
    the opportunity has no grounding text (a transient result wouldn't persist
    — warming would burn a model call per page view for nothing). Failures are
    logged, never raised: the warm is an optimization, not a dependency.
    """
    from app.database import SessionLocal

    if _is_inflight(user_id, opportunity_id):
        return  # already generating (another warm, or a live GET) — skip, don't queue
    try:
        db = SessionLocal()
        try:
            opp = db.get(Opportunity, opportunity_id)
            user = db.get(User, user_id)
            if opp is None or user is None:
                return
            if not (opp.description or "").strip():
                return  # nothing to ground in; result wouldn't be cacheable
            if _cached_analysis(db, opportunity_id, user_id) is not None:
                return
            ensure_analysis(db, opp, user)  # guard-aware; dedupes with live GETs
            log.info(
                "analysis pre-warmed",
                extra={"opportunity_id": opportunity_id, "user_id": user_id},
            )
        finally:
            db.close()
    except Exception:
        log.warning("analysis pre-warm failed", exc_info=True)


def _wait_for_inflight(
    db: Session, opportunity_id: str, user_id: int, *, timeout_s: float = 25.0
) -> AnalysisModel | None:
    """A generation is running elsewhere — wait for its row instead of paying
    for the same model call twice. Polls in short steps; on timeout the caller
    falls through to generating inline, exactly as before pre-warming existed."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _is_inflight(user_id, opportunity_id):
            break
        time.sleep(0.4)
        db.expire_all()  # fresh read — the warm wrote via another session
        row = _cached_analysis(db, opportunity_id, user_id)
        if row is not None:
            return row
    db.expire_all()
    return _cached_analysis(db, opportunity_id, user_id)


@router.get("/opportunities/{opportunity_id}/analysis", response_model=Analysis)
def get_analysis(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Analysis:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
    ensure_visible(opp, user)
    return _to_schema(ensure_analysis(db, opp, user))


@router.post("/llm/extract", response_model=list[Obligation])
def extract_obligations(
    req: ExtractRequest, user: User = Depends(current_user)
) -> list[Obligation]:
    """Kaliza's isolation harness: obligations for one raw chunk.

    The chunk is treated as a single unnamed section, so quotes verify against
    exactly the text that was sent in.
    """
    section = {"ref": "1", "heading": "", "text": req.chunk_text, "page": 1}
    return [Obligation(**o) for o in gateway.extract_obligations([section])]


@router.get("/llm/status")
def llm_status(user: User = Depends(current_user)) -> dict:
    return {
        "llm_mode": config.LLM_MODE,
        "model_id": config.BEDROCK_MODEL_ID if config.LLM_MODE == "bedrock" else None,
        "auth_mode": config.AUTH_MODE,
    }
