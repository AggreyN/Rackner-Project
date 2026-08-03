"""Live SAM.gov + USAspending — opt-in.

    RUN_GOV_TESTS=1 pytest tests/test_live_gov_apis.py

Skipped by default: CI must not fail because a government API is having a bad
morning, and SAM.gov requires a key. The offline suite (test_week3_api.py) uses
trimmed copies of real payloads, so mapping logic is covered there.

What this adds that stubs cannot: proof that the live services still return the
field names we map. These APIs change without notice, and a rename would
silently null out a column — `responseDeadLine` and `End Date` are both easy to
get wrong and neither is documented the way you'd expect.
"""

from __future__ import annotations

import datetime
import os

import pytest

from app.services import samgov, usaspending

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GOV_TESTS") != "1",
    reason="live government API test; set RUN_GOV_TESTS=1",
)


# --- SAM.gov ------------------------------------------------------------------


def test_sam_key_is_configured():
    if not samgov.is_configured():
        pytest.skip("SAM_GOV_API_KEY not set")


def test_sam_search_returns_mappable_records():
    if not samgov.is_configured():
        pytest.skip("SAM_GOV_API_KEY not set")
    results = samgov.search(limit=5, posted_days=14)
    assert results, "SAM.gov returned nothing for the last 14 days"
    for row in results:
        assert row["id"], "noticeId missing — did SAM rename it?"
        assert row["title"]
        assert row["kind"] in {
            "solicitation", "presolicitation", "sources_sought", "baa", "expiring_award",
        }


def test_sam_still_uses_the_capital_l_deadline_field():
    """Canary. If SAM renames responseDeadLine, every close_date goes null and
    the UI silently loses its countdown."""
    if not samgov.is_configured():
        pytest.skip("SAM_GOV_API_KEY not set")
    results = samgov.search(limit=20, posted_days=14)
    assert any(r["close_date"] for r in results), (
        "no result had a close_date — the deadline field may have been renamed"
    )


def test_sam_agency_is_derived_not_blank():
    if not samgov.is_configured():
        pytest.skip("SAM_GOV_API_KEY not set")
    results = samgov.search(limit=10, posted_days=14)
    assert any(r["agency"] for r in results), "fullParentPathName may have changed shape"


# --- USAspending (public, no key) ---------------------------------------------


def test_usaspending_end_date_field_still_exists():
    """Canary for the recompete radar's one indispensable field.

    The build spec called this "Period of Performance Current End Date", which
    does not exist in this API. The real name is "End Date". If that changes,
    the radar returns nothing and the failure is silent.
    """
    rows = usaspending._page(1, limit=5).get("results") or []
    assert rows, "USAspending returned no rows"
    assert any(r.get("End Date") for r in rows), (
        "no row had an 'End Date' — the field may have been renamed"
    )


def test_recompete_window_returns_awards_inside_it():
    today = datetime.date.today()
    results = usaspending.expiring_awards(from_months=12, to_months=18, limit=5)
    if not results:
        pytest.skip("no awards found in the 12-18 month window right now")
    for row in results:
        assert row["kind"] == "expiring_award"
        assert row["close_date"] is None, "an expiring award must have no response deadline"
        assert row["expiry_date"]
        months = (datetime.date.fromisoformat(row["expiry_date"]) - today).days / 30.44
        assert 11 <= months <= 19, f"{row['expiry_date']} is outside the requested window"


def test_no_absurd_expiry_dates_survive():
    """USAspending contains end dates in 3017 and 2109."""
    today = datetime.date.today()
    for row in usaspending.expiring_awards(from_months=12, to_months=18, limit=10):
        year = datetime.date.fromisoformat(row["expiry_date"]).year
        assert year <= today.year + 25, f"implausible expiry survived: {row['expiry_date']}"


def test_spend_summary_for_a_known_recipient():
    result = usaspending.spend_summary(
        opportunity_id="LIVE-1", recipient="LOCKHEED MARTIN CORPORATION"
    )
    assert result["years"], "no fiscal-year series returned"
    assert result["total_obligated"] > 0
    for year in result["years"]:
        assert year["fiscal_year"].startswith("FY")
        assert isinstance(year["amount"], float)
