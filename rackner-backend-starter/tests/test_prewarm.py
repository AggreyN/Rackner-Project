"""Analysis pre-warming (SCHEMA_v2 question 3, option (a)).

The contract under test: opening an opportunity detail quietly generates the
analysis in the background, so GET /analysis is a cache hit — and under no
interleaving does the same (user, opportunity) analysis get generated twice
concurrently (in bedrock mode a duplicate is a duplicate 30s model bill).

TestClient runs background tasks before the request returns, which makes the
warm DETERMINISTIC here: after client.get(detail) the warm has already run.
The concurrency paths (wait-for-inflight, dedupe) are tested directly against
the guard machinery with real threads.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.database import SessionLocal
from app.models import Analysis as AnalysisModel
from app.models import Opportunity
from app.routes import analysis as analysis_module

SOURCE = (
    "C.3.1 Incident Reporting\n"
    "The Contractor shall report any cyber incident within 72 hours."
)


def _seed(opp_id: str, description: str) -> None:
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id)
        if row is None:
            row = Opportunity(id=opp_id, title=f"Seed {opp_id}", agency="DoD")
            db.add(row)
        row.description = description
        # Reset any state a previous run left behind.
        db.query(AnalysisModel).filter_by(opportunity_id=opp_id).delete()
        from app.models import SourceDocument

        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.commit()
    finally:
        db.close()


def _analysis_rows(opp_id: str) -> int:
    db = SessionLocal()
    try:
        return db.query(AnalysisModel).filter_by(opportunity_id=opp_id).count()
    finally:
        db.close()


# --- the happy path -----------------------------------------------------------


def test_detail_view_prewarms_the_analysis(client, auth_headers):
    """After GET /opportunities/{id}, the analysis row already exists —
    without GET /analysis ever having been called."""
    _seed("WARM-1", SOURCE)
    assert _analysis_rows("WARM-1") == 0

    r = client.get("/opportunities/WARM-1", headers=auth_headers)
    assert r.status_code == 200, r.text

    assert _analysis_rows("WARM-1") == 1, "detail view should have pre-generated the analysis"


def test_prewarmed_analysis_is_served_as_cache_hit(client, auth_headers, monkeypatch):
    """The point of the feature: the later GET /analysis must not generate."""
    _seed("WARM-2", SOURCE)
    client.get("/opportunities/WARM-2", headers=auth_headers)  # warms
    assert _analysis_rows("WARM-2") == 1

    from app.llm import gateway

    def explode(*a, **k):
        raise AssertionError("GET /analysis regenerated despite the warm cache")

    monkeypatch.setattr(gateway, "analyze", explode)
    r = client.get("/opportunities/WARM-2/analysis", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["obligations"], "served analysis should be the grounded one"


def test_repeat_detail_views_do_not_stack_analyses(client, auth_headers):
    _seed("WARM-3", SOURCE)
    for _ in range(3):
        client.get("/opportunities/WARM-3", headers=auth_headers)
    assert _analysis_rows("WARM-3") == 1


def test_no_grounding_text_means_no_warm(client, auth_headers):
    """A warm against an empty document couldn't be cached (transient-only
    rule), so it must not fire at all — else every page view burns a model
    call for nothing in bedrock mode."""
    _seed("WARM-EMPTY", "")
    # kind=expiring_award so the detail route serves the bare row without
    # trying SAM (no key in tests).
    db = SessionLocal()
    try:
        db.get(Opportunity, "WARM-EMPTY").kind = "expiring_award"
        db.commit()
    finally:
        db.close()

    r = client.get("/opportunities/WARM-EMPTY", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert _analysis_rows("WARM-EMPTY") == 0


def test_prewarm_flag_off_disables_warming(client, auth_headers, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ANALYSIS_PREWARM", False)
    _seed("WARM-OFF", SOURCE)
    client.get("/opportunities/WARM-OFF", headers=auth_headers)
    assert _analysis_rows("WARM-OFF") == 0


def test_warm_failure_never_breaks_the_detail_response(client, auth_headers, monkeypatch):
    """The warm is an optimization. If generation explodes, the user still
    gets their opportunity."""
    from app.llm import gateway

    monkeypatch.setattr(gateway, "analyze", lambda *a, **k: 1 / 0)
    _seed("WARM-BOOM", SOURCE)
    r = client.get("/opportunities/WARM-BOOM", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert _analysis_rows("WARM-BOOM") == 0


# --- concurrency: never generate twice ----------------------------------------


def test_warm_skips_while_generation_is_inflight():
    """warm_analysis must be a no-op when the same (user, opp) is generating."""
    assert analysis_module._acquire(999, "WARM-INFLIGHT")
    try:
        called = {"n": 0}
        original = analysis_module.ensure_analysis

        def counting(*a, **k):
            called["n"] += 1
            return original(*a, **k)

        analysis_module.ensure_analysis = counting
        try:
            analysis_module.warm_analysis("WARM-INFLIGHT", 999)
        finally:
            analysis_module.ensure_analysis = original
        assert called["n"] == 0, "warm must skip, not queue, while inflight"
    finally:
        analysis_module._release(999, "WARM-INFLIGHT")


def test_get_waits_for_inflight_generation_instead_of_duplicating(
    client, auth_headers, monkeypatch
):
    """A GET arriving mid-warm must wait for the warm's row, not regenerate.

    Simulated with real threads: the 'warm' holds the guard, then lands a row
    ~0.6s later. gateway.analyze is rigged to explode, so the test fails loudly
    if the route falls back to generating."""
    _seed("WARM-RACE", SOURCE)

    from app.database import SessionLocal as SL
    from app.llm import gateway

    monkeypatch.setattr(
        gateway, "analyze", lambda *a, **k: (_ for _ in ()).throw(AssertionError("duplicated the inflight generation"))
    )

    # Find the test user's id for the guard key.
    db = SL()
    try:
        from app.models import User

        user_id = db.query(User).filter_by(email="pytest@rackner.com").one().id
    finally:
        db.close()

    assert analysis_module._acquire(user_id, "WARM-RACE")

    def fake_warm_completes():
        time.sleep(0.6)
        db = SL()
        try:
            db.add(
                AnalysisModel(
                    opportunity_id="WARM-RACE",
                    user_id=user_id,
                    score=61.0,
                    band="conditional",
                    verdict="landed by the in-flight warm",
                    factors=[],
                    obligations=[],
                )
            )
            db.commit()
        finally:
            db.close()
        analysis_module._release(user_id, "WARM-RACE")

    t = threading.Thread(target=fake_warm_completes)
    t.start()
    try:
        r = client.get("/opportunities/WARM-RACE/analysis", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["verdict"] == "landed by the in-flight warm"
    finally:
        t.join()
    assert _analysis_rows("WARM-RACE") == 1
