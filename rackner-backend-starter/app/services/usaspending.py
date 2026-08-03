"""USAspending: the recompete radar and spend history.

THE RECOMPETE PROBLEM
---------------------
The capture window is 12-18 months before an incumbent's period of performance
ends — early enough to shape the requirement and meet the CO before an RFP
exists. Finding those awards means querying by period-of-performance end date.

USAspending does not support that. `spending_by_award` filters time only by
action/signed/modified date, never by PoP end. (The field the build spec names,
"Period of Performance Current End Date", does not exist in this API at all —
the real field is "End Date", confirmed against the live service.)

It does, however, SORT by "End Date" server-side AND support keyset pagination.
Passing `last_record_sort_value` = the window's start date seeks straight to
the first award ending on or after it, and then we read forward until past the
window's end. One seek, then a bounded read.

Offset pagination is not an option here: USAspending rejects any page past
50,000 records ("Page #512 with limit 100 is over the maximum result limit"),
and the earliest end dates in this dataset are from 1995, so the window is
always far beyond that cap.

DATA QUALITY
------------
Real end dates in this dataset include 3017-04-30 and 2109-09-30. Anything
absurd is discarded rather than shown as a recompete in the year 3017.
"""

from __future__ import annotations

import datetime
import logging

from app.services.http import UpstreamError, post_json

log = logging.getLogger(__name__)

AWARD_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
OVER_TIME_URL = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
SERVICE = "USAspending.gov"

# Definitive contracts: D=definitive, A/B/C=IDV-derived orders.
_AWARD_TYPES = ["A", "B", "C", "D"]

_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Start Date",
    "End Date",
    "Award Amount",
    "Description",
    "naics_code",
    "naics_description",
    "generated_internal_id",
]

_PAGE_SIZE = 100
_MAX_PAGES_FORWARD = 15  # bounded read once the window is located

# An award ending more than this far out is bad data, not a capture target.
_MAX_PLAUSIBLE_YEARS = 25


def _page(
    page: int = 1,
    *,
    limit: int = _PAGE_SIZE,
    order: str = "asc",
    after_value: str | None = None,
    after_id: int | None = None,
) -> dict:
    """One page of awards sorted by End Date.

    With `after_value` this is a keyset seek — pass an ISO date to start at the
    first award ending on or after it. Both keyset parameters are required
    together; the API rejects the sort value alone.
    """
    body = {
        "filters": {
            "award_type_codes": _AWARD_TYPES,
            # Bound the candidate set to awards with recent activity; an award
            # last touched a decade ago is not a live recompete.
            "time_period": [
                {"start_date": "2019-01-01", "end_date": str(datetime.date.today())}
            ],
        },
        "fields": _FIELDS,
        "limit": limit,
        "page": page,
        "sort": "End Date",
        "order": order,
        "subawards": False,
    }
    if after_value is not None:
        body["last_record_sort_value"] = after_value
        body["last_record_unique_id"] = after_id if after_id is not None else 0

    return post_json(AWARD_SEARCH_URL, service=SERVICE, json=body, timeout=(5, 45))


def _end_date(row: dict) -> datetime.date | None:
    raw = row.get("End Date")
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _to_summary(row: dict, today: datetime.date) -> dict | None:
    end = _end_date(row)
    if end is None:
        return None
    if end.year > today.year + _MAX_PLAUSIBLE_YEARS:
        return None  # 3017-04-30 and friends

    months = round((end - today).days / 30.44)
    naics = row.get("naics_code")
    if isinstance(naics, dict):  # the API returns either shape
        naics = naics.get("code")
    amount = row.get("Award Amount")

    return {
        "id": row.get("generated_internal_id") or row.get("Award ID") or "",
        "title": (row.get("Description") or row.get("Award ID") or "Expiring award").strip()[:300],
        "agency": row.get("Awarding Agency") or "",
        "office": row.get("Awarding Sub Agency"),
        "solicitation_number": row.get("Award ID"),
        "naics": str(naics) if naics else None,
        "set_aside": None,
        "kind": "expiring_award",
        "description": row.get("Description") or "",
        # An expiring award is not open for response — no close date.
        "close_date": None,
        "days_to_close": None,
        "est_value": _format_value(amount),
        "incumbent": row.get("Recipient Name"),
        "fit_score": None,
        "expiry_date": end.isoformat(),
        "months_to_expiry": months,
        "current_award_value": float(amount) if amount is not None else None,
        "_source_url": (
            f"https://www.usaspending.gov/award/{row.get('generated_internal_id')}"
            if row.get("generated_internal_id")
            else ""
        ),
        "_description_url": "",
        "_point_of_contact": [],
        "_recipient_uei": row.get("Recipient UEI"),
    }


def _format_value(amount) -> str | None:
    """SCHEMA_v2's est_value is a display STRING, not a number."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= threshold:
            return f"${value / threshold:.1f}{suffix}"
    return f"${value:.0f}"


def expiring_awards(
    *,
    from_months: int = 12,
    to_months: int = 18,
    limit: int = 25,
    today: datetime.date | None = None,
) -> list[dict]:
    """Awards whose period of performance ends inside the window.

    The 12-18 month default is the capture sweet spot from SCHEMA_v2.
    """
    today = today or datetime.date.today()
    window_start = today + datetime.timedelta(days=int(from_months * 30.44))
    window_end = today + datetime.timedelta(days=int(to_months * 30.44))

    found: list[dict] = []
    pages_read = 0
    # Seek straight to the window's first award, then read forward.
    after_value: str | None = window_start.isoformat()
    after_id: int | None = 0
    exhausted = False

    while pages_read < _MAX_PAGES_FORWARD and len(found) < limit and not exhausted:
        payload = _page(after_value=after_value, after_id=after_id)
        rows = payload.get("results") or []
        pages_read += 1
        if not rows:
            break

        for row in rows:
            end = _end_date(row)
            if end is None or end < window_start:
                continue
            if end > window_end:
                # Ascending sort: everything after this is past the window.
                exhausted = True
                break
            summary = _to_summary(row, today)
            if summary:
                found.append(summary)
                if len(found) >= limit:
                    break

        meta = payload.get("page_metadata") or {}
        if not meta.get("hasNext"):
            break
        after_value = meta.get("last_record_sort_value") or after_value
        after_id = meta.get("last_record_unique_id") or 0

    if pages_read >= _MAX_PAGES_FORWARD and len(found) < limit:
        # No silent caps: say when coverage was bounded.
        log.info(
            "recompete radar stopped at the %d-page read cap with %d results "
            "(window %d-%d months)",
            _MAX_PAGES_FORWARD,
            len(found),
            from_months,
            to_months,
        )
    return found


def spend_summary(
    *,
    opportunity_id: str,
    recipient: str | None,
    agency: str | None = None,
    years: int = 6,
    today: datetime.date | None = None,
) -> dict:
    """The by-fiscal-year obligation series behind an opportunity.

    Keyed on the incumbent when we know one — that is the number that matters
    for a recompete ("how big is this actually?"). Without an incumbent there
    is nothing meaningful to total, so an empty series is returned rather than
    an invented one.
    """
    today = today or datetime.date.today()
    if not recipient:
        return {
            "opportunity_id": opportunity_id,
            "years": [],
            "total_obligated": 0.0,
            "incumbent": None,
            "trend_pct": None,
        }

    start = datetime.date(today.year - years, 10, 1)
    payload = post_json(
        OVER_TIME_URL,
        service=SERVICE,
        json={
            "group": "fiscal_year",
            "filters": {
                "award_type_codes": _AWARD_TYPES,
                "recipient_search_text": [recipient],
                "time_period": [{"start_date": str(start), "end_date": str(today)}],
            },
            "subawards": False,
        },
        timeout=(5, 45),
    )

    series = []
    for row in payload.get("results", []) or []:
        fiscal_year = (row.get("time_period") or {}).get("fiscal_year")
        amount = row.get("aggregated_amount")
        if fiscal_year is None or amount is None:
            continue
        series.append({"fiscal_year": f"FY{str(fiscal_year)[-2:]}", "amount": float(amount)})

    total = sum(y["amount"] for y in series)
    return {
        "opportunity_id": opportunity_id,
        "years": series,
        "total_obligated": total,
        "incumbent": {"name": recipient, "uei": ""},
        "trend_pct": _trend_pct(series),
    }


def _trend_pct(series: list[dict]) -> float | None:
    """Average year-over-year change, as a percentage.

    Needs at least two years with a non-zero base; otherwise null rather than a
    fabricated 0%.
    """
    usable = [y for y in series if y["amount"]]
    if len(usable) < 2:
        return None
    changes = []
    for previous, current in zip(usable, usable[1:]):
        if previous["amount"] > 0:
            changes.append((current["amount"] - previous["amount"]) / previous["amount"])
    if not changes:
        return None
    return round(sum(changes) / len(changes) * 100, 1)
