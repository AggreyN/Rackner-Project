"""Analysis endpoints — the LLM gateway's HTTP surface.

Per SCHEMA.md's handoff contract:
  POST /opportunities/{id}/analysis  → run the gateway, persist, return an Analysis
  GET  /opportunities/{id}/analysis  → the latest stored Analysis for this user

Plus two helpers:
  POST /llm/extract  → obligations for a raw chunk (lets Kaliza/frontend test in isolation)
  GET  /llm/status   → which mode the gateway is in (mock vs bedrock)

All routes are protected by `current_user`. The no-hallucination `verified` flag
is set inside the gateway, not here.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.auth import current_user
from app.database import get_db
from app.llm import gateway
from app.models import Analysis as AnalysisModel
from app.models import LifecycleProfile as LifecycleProfileModel
from app.models import Opportunity, User
from app.schemas import Analysis, LifecycleProfile, Obligation

router = APIRouter(tags=["analysis"])


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class AnalysisRequest(BaseModel):
    # The solicitation text obligations are extracted from + verified against.
    source_text: str | None = None
    # Override the lifecycle profile for this call; otherwise the user's saved one.
    lifecycle_profile: LifecycleProfile | None = None
    # Optional opportunity metadata, cached if we don't have this id yet.
    title: str | None = None
    agency: str | None = None
    naics: str | None = None
    set_aside: str | None = None
    description: str | None = None
    source_url: str | None = None


class ExtractRequest(BaseModel):
    chunk_text: str
    source_text: str | None = None


# --------------------------------------------------------------------------- #
# Helpers (ORM ↔ plain dict, matching SCHEMA.md field names)
# --------------------------------------------------------------------------- #
def _get_or_create_opportunity(
    db: Session, opp_id: str, req: AnalysisRequest
) -> Opportunity:
    opp = db.get(Opportunity, opp_id)
    if opp is None:
        opp = Opportunity(
            id=opp_id,
            title=req.title or "(untitled opportunity)",
            agency=req.agency or "(unknown agency)",
            naics=req.naics,
            set_aside=req.set_aside,
            description=req.description or (req.source_text or "")[:2000],
            source_url=req.source_url or "",
        )
        db.add(opp)
        db.commit()
        db.refresh(opp)
    return opp


def _opportunity_dict(opp: Opportunity) -> dict:
    return {
        "id": opp.id,
        "title": opp.title,
        "agency": opp.agency,
        "naics": opp.naics,
        "set_aside": opp.set_aside,
        "response_deadline": opp.response_deadline.isoformat()
        if opp.response_deadline
        else None,
        "estimated_value": float(opp.estimated_value)
        if opp.estimated_value is not None
        else None,
        "description": opp.description or "",
        "source_url": opp.source_url or "",
    }


def _lifecycle_dict(req: AnalysisRequest, db: Session, user: User) -> dict:
    if req.lifecycle_profile is not None:
        return req.lifecycle_profile.model_dump()
    lp = db.scalar(
        select(LifecycleProfileModel)
        .where(LifecycleProfileModel.user_id == user.id)
        .order_by(LifecycleProfileModel.updated_at.desc())
    )
    if lp is None:
        return LifecycleProfile().model_dump()
    return {
        "capabilities": lp.capabilities or [],
        "target_agencies": lp.target_agencies or [],
        "naics_codes": lp.naics_codes or [],
        "past_performance": lp.past_performance or [],
        "contract_vehicles": lp.contract_vehicles or [],
        "set_aside_status": lp.set_aside_status or [],
        "size_targets": {
            "min_value": float(lp.size_min or 0),
            "max_value": float(lp.size_max or 0),
        },
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.post("/opportunities/{opportunity_id}/analysis", response_model=Analysis)
def generate_analysis(
    opportunity_id: str,
    req: AnalysisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Run the LLM gateway for this opportunity + the user's profile, persist the
    result, and return it. Works with no AWS in mock mode."""
    opp = _get_or_create_opportunity(db, opportunity_id, req)
    profile = _lifecycle_dict(req, db, user)
    source_text = req.source_text or opp.description or ""

    result = gateway.analyze(_opportunity_dict(opp), profile, source_text=source_text)

    row = AnalysisModel(
        opportunity_id=opp.id,
        user_id=user.id,
        compatibility_score=result["compatibility_score"],
        verdict=result["verdict"],
        summary=result["summary"],
        factors=result["factors"],
        obligations=result["obligations"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    result["generated_at"] = row.generated_at.isoformat() if row.generated_at else None
    return result


@router.get("/opportunities/{opportunity_id}/analysis", response_model=Analysis)
def get_analysis(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Return the most recent stored Analysis for this user + opportunity."""
    row = db.scalar(
        select(AnalysisModel)
        .where(
            AnalysisModel.opportunity_id == opportunity_id,
            AnalysisModel.user_id == user.id,
        )
        .order_by(AnalysisModel.generated_at.desc())
    )
    if row is None:
        raise HTTPException(
            404, "No analysis yet for this opportunity — POST to generate one."
        )
    return {
        "opportunity_id": row.opportunity_id,
        "compatibility_score": row.compatibility_score,
        "verdict": row.verdict,
        "summary": row.summary,
        "factors": row.factors or [],
        "obligations": row.obligations or [],
        "spend": None,
        "contact": None,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }


@router.post("/llm/extract", response_model=list[Obligation])
def extract_obligations(
    req: ExtractRequest,
    user: User = Depends(current_user),
) -> list[dict]:
    """Extract + verify obligations from a raw text chunk. No DB write — handy
    for Kaliza to test her extractor output against the schema in isolation."""
    return gateway.extract_obligations(req.chunk_text, source_text=req.source_text)


@router.get("/llm/status")
def llm_status(user: User = Depends(current_user)) -> dict:
    """Which mode the gateway is in, so the frontend/Kaliza can tell mock apart
    from real Claude output."""
    return {
        "mode": config.LLM_MODE,
        "model_id": config.BEDROCK_MODEL_ID if config.LLM_MODE == "bedrock" else None,
    }
