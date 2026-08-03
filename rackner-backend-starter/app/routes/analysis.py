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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db
from app.llm import gateway
from app.models import Analysis as AnalysisModel
from app.models import LifecycleProfile as LifecycleProfileModel
from app.models import Opportunity, User
from app.routes.documents import get_or_build_document
from app.schemas import Analysis, Obligation

router = APIRouter(tags=["analysis"])


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
        score=row.score,
        band=row.band,
        verdict=row.verdict or "",
        factors=row.factors or [],
        obligations=row.obligations or [],
    )


def ensure_analysis(db: Session, opp: Opportunity, user: User) -> AnalysisModel:
    """Return this user's analysis for the opportunity, generating it on a miss.

    This is the (b)-option seam: safe to call from a background task or warm-up
    job. Generation reads the persisted SourceDocument sections, so obligations
    are verified against the same text `GET /document` serves.
    """
    row = db.scalar(
        select(AnalysisModel)
        .where(
            AnalysisModel.opportunity_id == opp.id,
            AnalysisModel.user_id == user.id,
        )
        .order_by(AnalysisModel.generated_at.desc())
    )
    if row is not None:
        return row

    doc = get_or_build_document(db, opp)
    result = gateway.analyze(
        _opportunity_dict(opp), _lifecycle_dict(db, user), doc.sections
    )

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
    if doc.sections:
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/opportunities/{opportunity_id}/analysis", response_model=Analysis)
def get_analysis(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Analysis:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
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
