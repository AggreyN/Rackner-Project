"""The search freshness ledger — repeat searches must be quota-free.

Search was the last live-first path: every query spent a SAM call even when
the answer was already cached. Now a (query, kinds) asked live within
SAM_SEARCH_TTL_HOURS serves cached rows with ZERO SAM calls; a stale or
unseen query spends exactly one live call and refreshes the ledger. The
SAM-down fallback stays beneath it all.
"""

from __future__ import annotations

import datetime

import pytest

from app import config
from app.database import SessionLocal
from app.models import SearchFetch
from app.services import samgov

SAM_ROW = {
    "id": "FRESH-1",
    "title": "Freshness ledger cyber services",
    "agency": "DoD",
    "office": None,
    "solicitation_number": "FRESH-26-Q-0001",
    "naics": "541512",
    "set_aside": None,
    "kind": "solicitation",
    "description": "",
    "close_date": None,
    "days_to_close": None,
    "est_value": None,
    "incumbent": None,
    "fit_score": None,
    "expiry_date": None,
    "months_to_expiry": None,
    "current_award_value": None,
}


@pytest.fixture(autouse=True)
def clean_ledger():
    db = SessionLocal()
    try:
        db.query(SearchFetch).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture()
def live_sam(monkeypatch):
    calls = {"n": 0}

    def fake_search(query, kinds=None, limit=25, **kw):
        calls["n"] += 1
        return [dict(SAM_ROW)]

    monkeypatch.setattr(samgov, "search", fake_search)
    monkeypatch.setattr(samgov, "is_configured", lambda: True)
    return calls


def test_repeat_search_spends_zero_sam_calls(client, auth_headers, live_sam):
    for i in range(3):
        r = client.get(
            "/opportunities/search?q=freshness+ledger+cyber&kinds=solicitation",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert any(row["id"] == "FRESH-1" for row in r.json()), f"attempt {i}"
    assert live_sam["n"] == 1, "only the FIRST search may spend a SAM call"


def test_distinct_queries_each_fetch_live(client, auth_headers, live_sam):
    client.get("/opportunities/search?q=alpha", headers=auth_headers)
    client.get("/opportunities/search?q=bravo", headers=auth_headers)
    assert live_sam["n"] == 2


def test_case_and_spacing_normalize_to_one_key(client, auth_headers, live_sam):
    client.get("/opportunities/search?q=Cyber+Services", headers=auth_headers)
    client.get("/opportunities/search?q=cyber+services+", headers=auth_headers)
    assert live_sam["n"] == 1


def test_stale_ledger_refreshes_live(client, auth_headers, live_sam):
    client.get("/opportunities/search?q=stale-test", headers=auth_headers)
    db = SessionLocal()
    try:
        row = db.query(SearchFetch).one()
        row.fetched_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=config.SAM_SEARCH_TTL_HOURS + 1
        )
        db.commit()
    finally:
        db.close()
    client.get("/opportunities/search?q=stale-test", headers=auth_headers)
    assert live_sam["n"] == 2, "an expired window must refetch live"


def test_failed_live_fetch_does_not_mark_fresh(client, auth_headers, monkeypatch):
    from app.services.http import UpstreamError

    calls = {"n": 0}

    def dying_search(query, kinds=None, limit=25, **kw):
        calls["n"] += 1
        raise UpstreamError("SAM.gov", "HTTP 429 (rate limited)")

    monkeypatch.setattr(samgov, "search", dying_search)
    monkeypatch.setattr(samgov, "is_configured", lambda: True)

    client.get("/opportunities/search?q=failing-query", headers=auth_headers)
    client.get("/opportunities/search?q=failing-query", headers=auth_headers)
    assert calls["n"] == 2, (
        "a FAILED fetch must not stamp the ledger — quota recovery has to retry"
    )


def test_ledger_key_is_bounded_for_any_query_length():
    from app.routes.opportunities import _sam_query_key

    huge = "cyber " * 500
    key = _sam_query_key(huge, ["solicitation"])
    assert len(key) == 64, "sha256 hex — a long query must never overflow the column"


def test_multiword_replay_matches_per_token(client, auth_headers, live_sam):
    """SAM's full-text is looser than a literal phrase; the replay matches
    per-word so 'ledger freshness' still finds the 'Freshness ledger...' row."""
    client.get("/opportunities/search?q=ledger+freshness+cyber", headers=auth_headers)
    r = client.get("/opportunities/search?q=ledger+freshness+cyber", headers=auth_headers)
    assert any(row["id"] == "FRESH-1" for row in r.json())
    assert live_sam["n"] == 1


def test_empty_replay_falls_through_to_live(client, auth_headers, live_sam, monkeypatch):
    """A fresh window whose replay matches nothing (for a non-empty q) must
    refetch live rather than serve a confident empty page."""
    client.get("/opportunities/search?q=zz-no-cached-row-matches", headers=auth_headers)
    client.get("/opportunities/search?q=zz-no-cached-row-matches", headers=auth_headers)
    # The stub always returns FRESH-1, which does NOT match this q in replay,
    # so both requests must have gone live.
    assert live_sam["n"] == 2


def test_closed_notices_do_not_resurface_from_cache(client, auth_headers, live_sam):
    """With one open and one closed cached row matching the query, the replay
    serves only the open one — dead deadlines never resurface from cache.
    (If ALL matches are closed, the replay is empty and correctly refetches
    live, covered by test_empty_replay_falls_through_to_live.)"""
    from app.database import SessionLocal
    from app.models import Opportunity

    client.get("/opportunities/search?q=freshness+ledger+cyber", headers=auth_headers)
    db = SessionLocal()
    try:
        db.get(Opportunity, "FRESH-1").close_date = (
            datetime.date.today() - datetime.timedelta(days=3)
        )
        db.add(
            Opportunity(
                id="FRESH-2",
                title="Freshness ledger cyber follow-on",
                agency="DoD",
                kind="solicitation",
                close_date=datetime.date.today() + datetime.timedelta(days=30),
            )
        )
        db.commit()
    finally:
        db.close()
    r = client.get("/opportunities/search?q=freshness+ledger+cyber", headers=auth_headers)
    ids = {row["id"] for row in r.json()}
    assert "FRESH-2" in ids, "the open cached row must serve"
    assert "FRESH-1" not in ids, "a notice past its close date must not resurface"
    assert live_sam["n"] == 1, "still zero extra SAM calls"
