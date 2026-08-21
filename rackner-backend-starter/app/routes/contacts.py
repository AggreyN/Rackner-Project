"""Contact discovery — human-in-the-loop by design.

    GET /opportunities/{id}/contact -> ContactResult

Results are cached per opportunity so repeated views are free and so the
address shown stays stable while a user works an opportunity.

`active_solicitation` is the Procurement Integrity Act guard: while a
solicitation is open, outreach is constrained and the UI must say so. This
endpoint proposes an address; it never sends anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db, ensure_visible
from app.models import Contact, Opportunity, User
from app.schemas import ContactResult
from app.services import email_discovery, samgov
from app.services.http import UpstreamError

router = APIRouter(tags=["contacts"])


def _to_schema(row: Contact, opp: Opportunity) -> ContactResult:
    return ContactResult(
        opportunity_id=row.opportunity_id,
        name=row.name,
        title=row.title or "",
        office=row.office or "",
        email=row.email or "",
        confidence=row.confidence,
        # Derived at serve time, never from the stored row: "open" is a
        # function of today's date, and Contact rows are cached forever — a
        # frozen flag kept warning about solicitations that closed months ago.
        active_solicitation=email_discovery._solicitation_open(
            {"kind": opp.kind, "close_date": opp.close_date}
        ),
    )


@router.get("/opportunities/{opportunity_id}/contact", response_model=ContactResult)
def get_contact(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ContactResult:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
    ensure_visible(opp, user)

    cached = db.scalar(select(Contact).where(Contact.opportunity_id == opportunity_id))
    if cached is not None:
        return _to_schema(cached, opp)

    # The published point-of-contact rides on the SAM notice, not on our cached
    # row, so re-fetch it. A SAM outage is not fatal here — fall through to
    # inference from what we already know.
    point_of_contact: list = []
    if opp.kind != "expiring_award" and samgov.is_configured():
        try:
            fetched = samgov.get_opportunity(opportunity_id)
            if fetched:
                point_of_contact = fetched.get("_point_of_contact") or []
        except UpstreamError:
            point_of_contact = []

    result = email_discovery.discover(
        {
            "id": opp.id,
            "agency": opp.agency,
            "office": opp.office,
            "kind": opp.kind,
            "close_date": opp.close_date.isoformat() if opp.close_date else None,
            "_point_of_contact": point_of_contact,
        }
    )
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No contact could be identified for this opportunity. Nothing was "
            "guessed — a fabricated address is worse than none.",
        )

    db.add(
        Contact(
            opportunity_id=result["opportunity_id"],
            name=result["name"],
            title=result["title"],
            office=result["office"],
            email=result["email"],
            confidence=result["confidence"],
            active_solicitation=result["active_solicitation"],
        )
    )
    db.commit()
    return ContactResult(**result)
