"""Spend history — follow the money.

    GET /opportunities/{id}/spend -> SpendSummary

USAspending is public, so no key is needed. Keyed on the incumbent when one is
known: for an expiring award that is the current holder, which is the number
that matters for a recompete. For a live solicitation with no known incumbent
there is nothing honest to total, so an empty series is returned rather than an
invented one — the UI shows "no spend history", not "$0".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import current_user, get_db, ensure_visible
from app.models import Opportunity, User
from app.schemas import SpendSummary
from app.services import usaspending
from app.services.http import UpstreamError

router = APIRouter(tags=["spend"])


@router.get("/opportunities/{opportunity_id}/spend", response_model=SpendSummary)
def get_spend(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> SpendSummary:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
    ensure_visible(opp, user)

    try:
        payload = usaspending.spend_summary(
            opportunity_id=opportunity_id,
            recipient=opp.incumbent,
            agency=opp.agency,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"{exc.service} is unavailable right now. {exc.detail}",
        ) from exc

    return SpendSummary(**payload)
