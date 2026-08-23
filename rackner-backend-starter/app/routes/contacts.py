"""Contact discovery — human-in-the-loop by design.

    GET /opportunities/{id}/contact -> ContactResult

Results are cached per opportunity so repeated views are free and so the
address shown stays stable while a user works an opportunity.

`active_solicitation` is the Procurement Integrity Act guard: while a
solicitation is open, outreach is constrained and the UI must say so. This
endpoint proposes an address; it never sends anything.
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db, ensure_visible
from app.models import Contact, Opportunity, User
from app.schemas import ContactResult, ContactVerification
from app.services import email_discovery, email_verify, samgov
from app.services.http import UpstreamError

router = APIRouter(tags=["contacts"])

_NO_CONTACT_DETAIL = (
    "No contact could be identified for this opportunity. Nothing was "
    "guessed — a fabricated address is worse than none."
)


def _maybe_reverify(db: Session, row: Contact) -> None:
    """Re-check a cached INFERRED address once its verification ages past the
    TTL (or was never checked). Tier-1 rows (confidence ≥ 0.8) are published
    by SAM and never verified. Records the outcome only — an "invalid" on a
    long-cached row updates the status the UI shows rather than churning the
    address out from under the user. Never raises."""
    if config.EMAIL_VERIFY_PROVIDER == "none" or not row.email:
        return
    if row.confidence >= 0.8:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    checked = row.verification_checked_at
    if checked is not None:
        if checked.tzinfo is None:  # SQLite returns naive datetimes
            checked = checked.replace(tzinfo=datetime.timezone.utc)
        if now - checked < datetime.timedelta(days=config.EMAIL_VERIFY_TTL_DAYS):
            return
    result = email_verify.verify(row.email)
    if not result.get("provider"):
        return  # no answer (cap, outage) — leave state so the next read retries
    row.verification_status = result["status"]
    row.verification_provider = result["provider"]
    row.verification_checked_at = now
    db.commit()


def _to_schema(row: Contact, opp: Opportunity) -> ContactResult:
    # Gated on the flag, not just the stored columns: SCHEMA_v2 promises
    # verification is ALWAYS null while the feature is off, including for
    # rows verified during an earlier flag-on period (the stored status
    # would only grow staler with re-verification disabled).
    verification = None
    if config.EMAIL_VERIFY_PROVIDER != "none" and row.verification_provider:
        verification = ContactVerification(
            provider=row.verification_provider,
            status=row.verification_status or "unknown",
            checked_at=row.verification_checked_at,
        )
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
        verification=verification,
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
        if not cached.email:
            # Negative cache: an earlier read proved every candidate invalid.
            # Without this row each read re-spent provider credits re-proving
            # the same thing — and a tripped daily cap then served the very
            # address the provider had just rejected. Re-discover only once
            # the verdict ages past the TTL (or the feature is off).
            checked = cached.verification_checked_at
            expired = checked is None or config.EMAIL_VERIFY_PROVIDER == "none"
            if not expired:
                if checked.tzinfo is None:
                    checked = checked.replace(tzinfo=datetime.timezone.utc)
                expired = datetime.datetime.now(
                    datetime.timezone.utc
                ) - checked >= datetime.timedelta(days=config.EMAIL_VERIFY_TTL_DAYS)
            if not expired:
                raise HTTPException(status.HTTP_404_NOT_FOUND, _NO_CONTACT_DETAIL)
            db.delete(cached)
            db.commit()
        else:
            _maybe_reverify(db, cached)
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
    if result is None or result.get("none_valid"):
        if result is not None:
            # All candidates proven invalid by the verifier — cache the
            # negative verdict (empty-email tombstone) so later reads don't
            # re-spend provider credits; re-discovered after the TTL.
            db.add(
                Contact(
                    opportunity_id=opportunity_id,
                    name="",
                    email="",
                    confidence=0.0,
                    verification_status="invalid",
                    verification_provider=config.EMAIL_VERIFY_PROVIDER,
                    verification_checked_at=datetime.datetime.now(
                        datetime.timezone.utc
                    ),
                )
            )
            db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NO_CONTACT_DETAIL)

    # A real provider answer (including accept_all/unknown) is worth keeping;
    # "unverified" with no provider (flag off, cap hit, outage) is not — null
    # columns let the cached-path TTL check try again later.
    raw_verification = result.pop("verification", None) or {}
    now = datetime.datetime.now(datetime.timezone.utc)
    verification = None
    if raw_verification.get("provider"):
        verification = ContactVerification(
            provider=raw_verification["provider"],
            status=raw_verification["status"],
            checked_at=now,
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
            verification_status=verification.status if verification else None,
            verification_provider=verification.provider if verification else None,
            verification_checked_at=now if verification else None,
        )
    )
    db.commit()
    return ContactResult(**result, verification=verification)
