"""Opportunity search, suggestions and detail.

    GET /opportunities/search?q=&kinds=&expiring_from=&expiring_to=
    GET /opportunities/suggested?kinds=&expiring_from=&expiring_to=
    GET /opportunities/{id}

These are what make the rest of the app reachable: /analysis and /document both
need an Opportunity row, and this is what creates them. Results are upserted
into the cache so a later detail request doesn't depend on the upstream still
being available.

Two sources behind one shape. Live notices come from SAM.gov; `expiring_award`
rows come from USAspending's recompete radar. `kinds` decides which are
queried, so asking only for expiring awards costs no SAM call and vice versa.

Filtering is server-side by contract — the recompete radar spans the whole
award set and cannot be paged into the browser.
"""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.models import LifecycleProfile as LifecycleProfileModel
from app.models import Opportunity, User
from app.schemas import OpportunitySummary
from app.services import fit, samgov, usaspending
from app.services.http import UpstreamError

log = logging.getLogger(__name__)

router = APIRouter(tags=["opportunities"])

SAM_KINDS = {"solicitation", "presolicitation", "sources_sought", "baa"}


def _fail(exc: UpstreamError) -> HTTPException:
    """Upstream trouble becomes a 503 naming the service — never a silent
    empty list, which the UI would render as 'nothing exists'."""
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        f"{exc.service} is unavailable right now. {exc.detail}",
    )


def _parse_kinds(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def _lifecycle(db: Session, user: User) -> dict | None:
    row = db.scalar(
        select(LifecycleProfileModel)
        .where(LifecycleProfileModel.user_id == user.id)
        .order_by(LifecycleProfileModel.updated_at.desc())
    )
    if row is None:
        return None
    return {
        "capabilities": row.capabilities or [],
        "naics_codes": row.naics_codes or [],
        "target_agencies": row.target_agencies or [],
        "set_asides": row.set_aside_status or [],
    }


def _cache(db: Session, summaries: list[dict]) -> None:
    """Upsert by id so detail/analysis work after the search that found them."""
    for s in summaries:
        if not s.get("id"):
            continue
        row = db.get(Opportunity, s["id"])
        if row is None:
            row = Opportunity(id=s["id"])
            db.add(row)
        row.title = s.get("title") or ""
        row.agency = s.get("agency") or ""
        row.office = s.get("office")
        row.solicitation_number = s.get("solicitation_number")
        row.naics = s.get("naics")
        row.set_aside = s.get("set_aside")
        row.kind = s.get("kind") or "solicitation"
        row.source_url = s.get("_source_url") or ""
        row.est_value = s.get("est_value")
        row.incumbent = s.get("incumbent")
        row.current_award_value = s.get("current_award_value")
        for field, key in (("close_date", "close_date"), ("expiry_date", "expiry_date")):
            raw = s.get(key)
            setattr(row, field, datetime.date.fromisoformat(raw) if raw else None)
        # Only overwrite a stored description with a non-empty one: the search
        # payload has none, and blanking it would destroy the grounding text a
        # previous detail fetch already stored.
        if s.get("description"):
            row.description = s["description"]
    db.commit()


def _to_summary(row: Opportunity, today: datetime.date | None = None) -> dict:
    """Cached row -> OpportunitySummary. The two derived fields are computed at
    serialization, never stored, so they can't go stale in the database."""
    today = today or datetime.date.today()
    months = (
        round((row.expiry_date - today).days / 30.44) if row.expiry_date else None
    )
    return {
        "id": row.id,
        "title": row.title,
        "agency": row.agency,
        "office": row.office,
        "solicitation_number": row.solicitation_number,
        "naics": row.naics,
        "set_aside": row.set_aside,
        "kind": row.kind,
        "description": row.description or "",
        "close_date": row.close_date.isoformat() if row.close_date else None,
        "days_to_close": (row.close_date - today).days if row.close_date else None,
        "est_value": row.est_value,
        "incumbent": row.incumbent,
        "fit_score": None,
        "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
        "months_to_expiry": months,
        "current_award_value": (
            float(row.current_award_value) if row.current_award_value is not None else None
        ),
    }


def _clean(summaries: list[dict]) -> list[OpportunitySummary]:
    """Drop the internal underscore keys before they reach the wire."""
    return [
        OpportunitySummary(**{k: v for k, v in s.items() if not k.startswith("_")})
        for s in summaries
    ]


def _collect(
    *,
    query: str,
    kinds: list[str],
    expiring_from: int | None,
    expiring_to: int | None,
    limit: int,
) -> list[dict]:
    """Query whichever sources the requested kinds imply."""
    wants_expiring = (not kinds) or ("expiring_award" in kinds)
    wants_live = (not kinds) or bool(set(kinds) & SAM_KINDS)

    results: list[dict] = []
    if wants_live:
        results.extend(
            samgov.search(query, kinds=[k for k in kinds if k in SAM_KINDS] or None, limit=limit)
        )
    if wants_expiring:
        results.extend(
            usaspending.expiring_awards(
                from_months=expiring_from if expiring_from is not None else 12,
                to_months=expiring_to if expiring_to is not None else 18,
                limit=limit,
            )
        )
    return results


@router.get("/opportunities/search", response_model=list[OpportunitySummary])
def search_opportunities(
    q: str = Query("", description="free-text title search"),
    kinds: str | None = Query(None, description="comma-separated OpportunityKind list"),
    expiring_from: int | None = Query(None, description="months, expiring_award only"),
    expiring_to: int | None = Query(None, description="months, expiring_award only"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[OpportunitySummary]:
    try:
        results = _collect(
            query=q,
            kinds=_parse_kinds(kinds),
            expiring_from=expiring_from,
            expiring_to=expiring_to,
            limit=limit,
        )
    except UpstreamError as exc:
        raise _fail(exc) from exc

    _cache(db, results)
    fit.rank(results, _lifecycle(db, user))
    return _clean(results)


@router.get("/opportunities/suggested", response_model=list[OpportunitySummary])
def suggested_opportunities(
    kinds: str | None = Query(None),
    expiring_from: int | None = Query(None),
    expiring_to: int | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[OpportunitySummary]:
    """Ranked against the user's lifecycle plan.

    With no plan on file this degrades to an unranked feed (every fit_score
    null) rather than erroring — a new user should still see the market.
    """
    lifecycle = _lifecycle(db, user)
    try:
        results = _collect(
            query="",
            kinds=_parse_kinds(kinds),
            expiring_from=expiring_from,
            expiring_to=expiring_to,
            limit=limit,
        )
    except UpstreamError as exc:
        raise _fail(exc) from exc

    _cache(db, results)
    fit.rank(results, lifecycle)
    return _clean(results)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunitySummary)
def get_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> OpportunitySummary:
    """Cached if we have it, otherwise fetched from SAM.gov and cached.

    The description is fetched here and not during search: it is a second
    round-trip per notice, and it is what /document grounds obligations in.
    """
    row = db.get(Opportunity, opportunity_id)
    if row is not None and (row.description or row.kind == "expiring_award"):
        summary = _to_summary(row)
        summary["fit_score"] = fit.score(summary, _lifecycle(db, user))
        return OpportunitySummary(**summary)

    try:
        fetched = samgov.get_opportunity(opportunity_id)
    except UpstreamError as exc:
        if row is not None:
            summary = _to_summary(row)  # serve stale rather than nothing
            summary["fit_score"] = fit.score(summary, _lifecycle(db, user))
            return OpportunitySummary(**summary)
        raise _fail(exc) from exc

    if fetched is None:
        if row is not None:
            summary = _to_summary(row)
            summary["fit_score"] = fit.score(summary, _lifecycle(db, user))
            return OpportunitySummary(**summary)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")

    fetched["description"] = samgov.fetch_description(fetched.get("_description_url", ""))
    _cache(db, [fetched])
    fetched["fit_score"] = fit.score(fetched, _lifecycle(db, user))
    return _clean([fetched])[0]
