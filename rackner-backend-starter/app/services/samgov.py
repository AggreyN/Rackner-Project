"""SAM.gov Get Opportunities → OpportunitySummary.

Field names below were read off a live response, not the docs — several differ
from what you'd guess:

  * `description` is a URL, not text. The description lives behind a second
    call that returns {"description": "<html>"}, and that call has been measured
    taking over a minute. So it is fetched only on the detail path, with a short
    timeout, and its failure degrades to an empty description rather than
    failing the request.
  * the deadline field is `responseDeadLine` (capital L).
  * `fullParentPathName` is a dotted hierarchy —
    "DEPT OF DEFENSE.DEPT OF THE ARMY.NATIONAL GUARD BUREAU..." — so agency is
    the first segment and office the last.
  * `pointOfContact` carries real contracting-officer emails, which is why
    email_discovery prefers it over guessing address syntaxes.

SAM.gov has no dollar-value field, so `est_value` stays null on solicitations;
only expiring awards (USAspending) carry a value.
"""

from __future__ import annotations

import datetime
import html
import logging
import re

from app import config
from app.services.http import UpstreamError, get_json

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
SERVICE = "SAM.gov"

# SAM `type` / `baseType` -> SCHEMA_v2 OpportunityKind.
_KIND_BY_TYPE = {
    "solicitation": "solicitation",
    "combined synopsis/solicitation": "solicitation",
    "presolicitation": "presolicitation",
    "sources sought": "sources_sought",
    "special notice": "baa",
    "srcsgt": "sources_sought",
    "ssale": "solicitation",
}

# SCHEMA_v2 kind -> SAM `ptype` code, for server-side filtering.
_PTYPE_BY_KIND = {
    "solicitation": "o",
    "presolicitation": "p",
    "sources_sought": "r",
    "baa": "s",
}

_TAGS = re.compile(r"<[^>]+>")


def is_configured() -> bool:
    return bool(config.SAM_GOV_API_KEY)


def _require_key() -> str:
    if not config.SAM_GOV_API_KEY:
        raise UpstreamError(SERVICE, "SAM_GOV_API_KEY is not configured")
    return config.SAM_GOV_API_KEY


def html_to_text(raw: str) -> str:
    """SAM descriptions are HTML fragments. Strip to plain text.

    Block-level tags become newlines so the ingest section splitter still sees
    document structure; everything else is dropped and entities unescaped.
    """
    if not raw:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "  - ", text)
    text = _TAGS.sub("", text)
    text = html.unescape(text)
    # Collapse the runs of blank lines the tag stripping leaves behind. Safe:
    # this happens BEFORE the text is stored or quoted against.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _kind_for(record: dict) -> str:
    raw = (record.get("type") or record.get("baseType") or "").strip().lower()
    return _KIND_BY_TYPE.get(raw, "solicitation")


def _agency_and_office(record: dict) -> tuple[str, str | None]:
    path = (record.get("fullParentPathName") or "").strip()
    if not path:
        return (record.get("organizationType") or "", None)
    parts = [p.strip() for p in path.split(".") if p.strip()]
    agency = parts[0].title() if parts else ""
    office = parts[-1].title() if len(parts) > 1 else None
    return agency, office


def _parse_date(value: str | None) -> datetime.date | None:
    """SAM mixes plain dates and ISO timestamps with offsets."""
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        return None


def days_until(day: datetime.date | None, *, today: datetime.date | None = None) -> int | None:
    if day is None:
        return None
    return (day - (today or datetime.date.today())).days


def to_summary(record: dict, *, today: datetime.date | None = None) -> dict:
    """One SAM record -> an OpportunitySummary-shaped dict.

    Recompete fields stay null here: a live solicitation has no expiring award
    behind it. Those come from usaspending.py.
    """
    agency, office = _agency_and_office(record)
    close = _parse_date(record.get("responseDeadLine"))
    return {
        "id": record.get("noticeId") or "",
        "title": (record.get("title") or "").strip(),
        "agency": agency,
        "office": office,
        "solicitation_number": record.get("solicitationNumber"),
        "naics": record.get("naicsCode"),
        "set_aside": record.get("typeOfSetAsideDescription") or record.get("typeOfSetAside"),
        "kind": _kind_for(record),
        "description": "",  # filled by fetch_description() on the detail path
        "close_date": close.isoformat() if close else None,
        "days_to_close": days_until(close, today=today),
        "est_value": None,  # SAM.gov exposes no dollar value
        "incumbent": None,
        "fit_score": None,  # set by the caller once a lifecycle plan is known
        "expiry_date": None,
        "months_to_expiry": None,
        "current_award_value": None,
        # Not part of SCHEMA_v2; carried internally for caching + contacts.
        "_source_url": record.get("uiLink") or "",
        "_description_url": record.get("description") or "",
        "_point_of_contact": record.get("pointOfContact") or [],
        # The full solicitation package (SOW, instructions, clauses) lives
        # behind these download URLs, not in the description.
        "_resource_links": record.get("resourceLinks") or [],
    }


def search(
    query: str = "",
    *,
    kinds: list[str] | None = None,
    limit: int = 25,
    posted_days: int = 90,
    today: datetime.date | None = None,
) -> list[dict]:
    """Search SAM.gov. Raises UpstreamError when the key is missing or SAM is down.

    SAM requires a posted-date window, so `posted_days` bounds how far back to
    look rather than being a user-facing filter.
    """
    key = _require_key()
    today = today or datetime.date.today()
    params = {
        "api_key": key,
        "limit": max(1, min(limit, 100)),
        "postedFrom": (today - datetime.timedelta(days=posted_days)).strftime("%m/%d/%Y"),
        "postedTo": today.strftime("%m/%d/%Y"),
    }
    if query:
        params["title"] = query

    # Only SAM-backed kinds are meaningful here; expiring_award comes from
    # USAspending and is filtered out by the caller.
    ptypes = [_PTYPE_BY_KIND[k] for k in (kinds or []) if k in _PTYPE_BY_KIND]
    if ptypes:
        params["ptype"] = ",".join(ptypes)

    payload = get_json(SEARCH_URL, service=SERVICE, params=params)
    return [to_summary(r, today=today) for r in payload.get("opportunitiesData", [])]


def get_opportunity(notice_id: str, *, today: datetime.date | None = None) -> dict | None:
    """Fetch one notice by id. Returns None when SAM has no such record.

    SAM v2 requires postedFrom/postedTo on EVERY request — including noticeid
    lookups — and rejects windows over one year. So this looks back the maximum
    364 days; a notice older than that isn't findable by id here, and the
    caller falls back to its cached row.
    """
    key = _require_key()
    today = today or datetime.date.today()
    payload = get_json(
        SEARCH_URL,
        service=SERVICE,
        params={
            "api_key": key,
            "noticeid": notice_id,
            "limit": 1,
            "postedFrom": (today - datetime.timedelta(days=364)).strftime("%m/%d/%Y"),
            "postedTo": today.strftime("%m/%d/%Y"),
        },
    )
    records = payload.get("opportunitiesData") or []
    return to_summary(records[0], today=today) if records else None


def fetch_description(description_url: str) -> str:
    """Fetch and de-HTML a notice description.

    Degrades to "" instead of raising: a slow description endpoint must not
    take down the opportunity detail view. Measured >60s in the wild, hence the
    short read timeout.
    """
    if not description_url:
        return ""
    try:
        payload = get_json(
            description_url,
            service=SERVICE,
            params={"api_key": config.SAM_GOV_API_KEY},
            timeout=(5, 15),
        )
    except UpstreamError as exc:
        log.info("description unavailable, continuing without it: %s", exc)
        return ""
    return html_to_text(payload.get("description") or "")
