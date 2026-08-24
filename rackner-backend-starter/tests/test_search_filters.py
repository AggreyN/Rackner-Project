"""Kaliza's SAM search-filter changes (2026-08-24).

1. ptype narrows to actionable notice types: o (Solicitation) + k (Combined
   Synopsis/Solicitation — SAM's own UI folds it into the Solicitation
   bucket, as does our kind mapping) + r (Sources Sought) by default;
   kinds=solicitation now sends o,k.
2. Runway floor: notices closing sooner than SAM_MIN_RUNWAY_DAYS are dropped
   from search/suggested — on the LIVE path before scoring/persisting AND on
   the cached replay path, so both agree. Dateless notices (the common
   Sources Sought shape) are always kept. 0 disables (the suite default).
"""

from __future__ import annotations

import datetime

import pytest

from app import config
from app.database import SessionLocal
from app.models import Opportunity, SearchFetch
from app.routes.opportunities import _runway_ok
from app.services import samgov

TODAY = datetime.date.today()


def _row(id_: str, close: datetime.date | None) -> dict:
    return {
        "id": id_,
        "title": f"Runwayzq filterzq target {id_}",
        "agency": "DoD",
        "office": None,
        "solicitation_number": id_,
        "naics": "541512",
        "set_aside": None,
        "kind": "solicitation",
        "description": "",
        "close_date": close.isoformat() if close else None,
        "days_to_close": (close - TODAY).days if close else None,
        "est_value": None,
        "incumbent": None,
        "fit_score": None,
        "expiry_date": None,
        "months_to_expiry": None,
        "current_award_value": None,
    }


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    db = SessionLocal()
    try:
        db.query(SearchFetch).delete()
        db.query(Opportunity).filter(Opportunity.id.like("RWY-%")).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
    yield


# --- change 1: ptype ---------------------------------------------------------


def _captured_params(monkeypatch):
    seen = {}

    def fake_get_json(url, *, service=None, params=None, **kw):
        seen.update(params or {})
        return {"opportunitiesData": []}

    monkeypatch.setattr(samgov, "get_json", fake_get_json)
    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "test-key")
    return seen


def test_default_search_sends_actionable_ptypes_only(monkeypatch):
    seen = _captured_params(monkeypatch)
    samgov.search("cyber")
    assert seen["ptype"] == "o,k,r"


def test_solicitation_kind_includes_combined_synopsis(monkeypatch):
    seen = _captured_params(monkeypatch)
    samgov.search("cyber", kinds=["solicitation"])
    assert seen["ptype"] == "o,k"


def test_sources_sought_kind_maps_to_r(monkeypatch):
    seen = _captured_params(monkeypatch)
    samgov.search("cyber", kinds=["sources_sought"])
    assert seen["ptype"] == "r"


# --- change 2: runway floor --------------------------------------------------


class TestRunwayPredicate:
    def test_dateless_is_kept(self, monkeypatch):
        monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
        assert _runway_ok({"close_date": None}) is True

    def test_unparseable_is_kept(self, monkeypatch):
        monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
        assert _runway_ok({"close_date": "TBD"}) is True

    def test_near_close_is_dropped_far_is_kept(self, monkeypatch):
        monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
        near = (TODAY + datetime.timedelta(days=30)).isoformat()
        far = (TODAY + datetime.timedelta(days=120)).isoformat()
        assert _runway_ok({"close_date": near}) is False
        assert _runway_ok({"close_date": far}) is True

    def test_zero_disables_the_floor(self, monkeypatch):
        monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 0)
        near = (TODAY + datetime.timedelta(days=1)).isoformat()
        assert _runway_ok({"close_date": near}) is True


def test_runway_filters_live_results_before_persist_and_replay_agrees(
    client, auth_headers, monkeypatch
):
    monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
    rows = [
        _row("RWY-NEAR", TODAY + datetime.timedelta(days=30)),
        _row("RWY-FAR", TODAY + datetime.timedelta(days=120)),
        _row("RWY-DATELESS", None),
    ]
    calls = {"n": 0}

    def fake_search(query, kinds=None, limit=25, **kw):
        calls["n"] += 1
        return [dict(r) for r in rows]

    monkeypatch.setattr(samgov, "search", fake_search)
    monkeypatch.setattr(samgov, "is_configured", lambda: True)

    r = client.get(
        "/opportunities/search?q=runwayzq+filterzq&kinds=solicitation",
        headers=auth_headers,
    )
    assert r.status_code == 200
    ids = {o["id"] for o in r.json()}
    assert ids == {"RWY-FAR", "RWY-DATELESS"}
    assert calls["n"] == 1

    # The floor is a SERVE-time filter, never a cache filter: the near-close
    # row must be persisted (the ledger's replay depends on the full page)
    # even though it is absent from the response.
    db = SessionLocal()
    try:
        assert db.get(Opportunity, "RWY-NEAR") is not None
        assert db.get(Opportunity, "RWY-FAR") is not None
    finally:
        db.close()

    # Replay (fresh ledger, zero further SAM calls) returns the same set.
    r = client.get(
        "/opportunities/search?q=runwayzq+filterzq&kinds=solicitation",
        headers=auth_headers,
    )
    assert {o["id"] for o in r.json()} == {"RWY-FAR", "RWY-DATELESS"}
    assert calls["n"] == 1


def test_fully_floored_page_still_replays_for_free(client, auth_headers, monkeypatch):
    """Review finding (breaking): a page whose EVERY row fails the floor must
    not defeat the freshness ledger — repeats serve the legit empty page from
    cache instead of burning a live SAM call each time."""
    monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
    calls = {"n": 0}

    def fake_search(query, kinds=None, limit=25, **kw):
        calls["n"] += 1
        return [
            _row("RWY-N1", TODAY + datetime.timedelta(days=20)),
            _row("RWY-N2", TODAY + datetime.timedelta(days=45)),
        ]

    monkeypatch.setattr(samgov, "search", fake_search)
    monkeypatch.setattr(samgov, "is_configured", lambda: True)
    for _ in range(3):
        r = client.get(
            "/opportunities/search?q=runwayzq+filterzq&kinds=solicitation",
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json() == []
    assert calls["n"] == 1, "repeats of a floored-empty query must be free"


def test_floor_on_fetches_a_full_page_per_call(monkeypatch):
    """One SAM call costs the same at limit=100 — with the floor on, fetch the
    full page so a small page of near-close rows can't zero out the results."""
    monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
    seen = _captured_params(monkeypatch)
    samgov.search("cyber", limit=100)
    assert seen["limit"] == 100


def test_no_kinds_replay_matches_live_default_kinds(client, auth_headers, monkeypatch):
    """Review finding: live default now excludes presolicitation/baa (ptype
    o,k,r) — the cached replay must exclude them too, or identical
    consecutive searches flip-flop."""
    monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 0)
    monkeypatch.setattr(
        samgov, "search", lambda *a, **k: [_row("RWY-SOL9", TODAY + datetime.timedelta(days=120))]
    )
    monkeypatch.setattr(samgov, "is_configured", lambda: True)
    client.get("/opportunities/search?q=runwayzq+filterzq", headers=auth_headers)
    db = SessionLocal()
    try:
        for id_, kind in (("RWY-PRESOL", "presolicitation"), ("RWY-BAA", "baa")):
            db.add(
                Opportunity(
                    id=id_,
                    title="Runwayzq filterzq target noise",
                    agency="DoD",
                    kind=kind,
                    close_date=TODAY + datetime.timedelta(days=200),
                )
            )
        db.commit()
    finally:
        db.close()
    # Replay of the same no-kinds query: the noise kinds must NOT resurface.
    r = client.get("/opportunities/search?q=runwayzq+filterzq", headers=auth_headers)
    ids = {o["id"] for o in r.json()}
    assert "RWY-PRESOL" not in ids and "RWY-BAA" not in ids
    assert "RWY-SOL9" in ids
    # An EXPLICIT presolicitation filter still reaches them from cache.
    from app.routes.opportunities import _cached_sam_rows

    db = SessionLocal()
    try:
        rows = _cached_sam_rows(
            db, query="runwayzq filterzq", kinds=["presolicitation"], limit=25
        )
        assert {r_["id"] for r_ in rows} == {"RWY-PRESOL"}
    finally:
        db.close()


def test_replay_excludes_rows_that_slipped_in_under_the_floor(
    client, auth_headers, monkeypatch
):
    """A near-close row already in the cache (e.g. persisted by a direct
    detail view) must not surface in list replays while the floor is on."""
    monkeypatch.setattr(config, "SAM_MIN_RUNWAY_DAYS", 90)
    monkeypatch.setattr(samgov, "search", lambda *a, **k: [
        _row("RWY-FAR2", TODAY + datetime.timedelta(days=120))
    ])
    monkeypatch.setattr(samgov, "is_configured", lambda: True)
    client.get(
        "/opportunities/search?q=runwayzq+filterzq&kinds=solicitation",
        headers=auth_headers,
    )
    db = SessionLocal()
    try:
        db.add(
            Opportunity(
                id="RWY-SLIPPED",
                title="Runwayzq filterzq target slipped",
                agency="DoD",
                kind="solicitation",
                close_date=TODAY + datetime.timedelta(days=10),
            )
        )
        db.commit()
    finally:
        db.close()
    r = client.get(
        "/opportunities/search?q=runwayzq+filterzq&kinds=solicitation",
        headers=auth_headers,
    )
    ids = {o["id"] for o in r.json()}
    assert "RWY-SLIPPED" not in ids
    assert "RWY-FAR2" in ids
