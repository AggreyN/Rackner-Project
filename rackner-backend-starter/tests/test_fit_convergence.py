"""Fit scores that converge instead of mislead.

The incident: a card showed "est. 69" while the full analysis said 87 — same
gauge, different instruments, no labeling. The rules now:
  * once a user's ANALYSIS exists, its score IS the card score
    (fit_source="analysis") — the two screens can never disagree;
  * everything else is a labeled ESTIMATE: a batched AI pre-screen in bedrock
    mode (one model call per page, cached per user, zero SAM calls), the
    deterministic heuristic in mock mode or on model failure;
  * cached estimates are stable across requests and die with the plan that
    produced them.
"""

from __future__ import annotations

import io

import pytest

from app import config
from app.database import SessionLocal
from app.llm import gateway
from app.models import Analysis, FitEstimate, Opportunity, User
from app.routes.opportunities import _apply_fit

LIFECYCLE = {
    "capabilities": ["cybersecurity", "cloud"],
    "naics_codes": ["541512"],
    "target_agencies": ["DoD"],
    "set_asides": [],
}


def _seed_opps(ids: list[str]) -> None:
    db = SessionLocal()
    try:
        for oid in ids:
            row = db.get(Opportunity, oid) or Opportunity(
                id=oid, title=f"Cybersecurity services {oid}", agency="DoD"
            )
            row.naics = "541512"
            db.add(row)
        db.commit()
    finally:
        db.close()


def _user(email: str = "pytest@rackner.com") -> User:
    db = SessionLocal()
    try:
        return db.query(User).filter_by(email=email).one()
    finally:
        db.close()


def _rows(ids: list[str]) -> list[dict]:
    return [
        {"id": oid, "title": f"Cybersecurity services {oid}", "agency": "DoD", "naics": "541512"}
        for oid in ids
    ]


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clean_estimates(client, auth_headers):
    yield
    db = SessionLocal()
    try:
        db.query(FitEstimate).delete()
        db.query(Analysis).filter(Analysis.opportunity_id.like("FIT-%")).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


# --- precedence ----------------------------------------------------------------


def test_analysis_score_wins_on_the_card(db, client, auth_headers):
    _seed_opps(["FIT-A"])
    user = _user()
    db.add(
        Analysis(
            opportunity_id="FIT-A", user_id=user.id, score=87.0, band="pursue",
            verdict="strong", factors=[], obligations=[],
        )
    )
    db.commit()
    rows = _rows(["FIT-A"])
    _apply_fit(db, user, rows, LIFECYCLE)
    assert rows[0]["fit_score"] == 87.0
    assert rows[0]["fit_source"] == "analysis", (
        "once analyzed, the card and the analysis screen must agree"
    )


def test_mock_mode_estimates_via_heuristic(db, client, auth_headers, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "mock")
    _seed_opps(["FIT-B"])
    rows = _rows(["FIT-B"])
    _apply_fit(db, _user(), rows, LIFECYCLE)
    assert rows[0]["fit_score"] is not None
    assert rows[0]["fit_source"] == "estimate"


def test_no_plan_means_null_and_unlabeled(db, client, auth_headers):
    _seed_opps(["FIT-C"])
    rows = _rows(["FIT-C"])
    _apply_fit(db, _user(), rows, None)
    assert rows[0]["fit_score"] is None
    assert rows[0]["fit_source"] is None


# --- the AI pre-screen ---------------------------------------------------------


def test_ai_prescreen_is_batched_cached_and_stable(db, client, auth_headers, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    calls = {"n": 0}

    def fake_prescreen(profile, rows):
        calls["n"] += 1
        return {r["id"]: 66.0 for r in rows}

    monkeypatch.setattr(gateway, "prescreen_scores", fake_prescreen)
    _seed_opps(["FIT-D1", "FIT-D2"])
    user = _user()

    rows = _rows(["FIT-D1", "FIT-D2"])
    _apply_fit(db, user, rows, LIFECYCLE)
    assert {r["fit_score"] for r in rows} == {66.0}
    assert {r["fit_source"] for r in rows} == {"estimate"}

    rows2 = _rows(["FIT-D1", "FIT-D2"])
    _apply_fit(db, user, rows2, LIFECYCLE)
    assert calls["n"] == 1, "second request must reuse cached estimates"
    assert {r["fit_score"] for r in rows2} == {66.0}, "the number must be stable"


def test_prescreen_failure_falls_back_to_heuristic(db, client, auth_headers, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")

    def boom(profile, rows):
        raise RuntimeError("bedrock throttled")

    monkeypatch.setattr(gateway, "prescreen_scores", boom)
    _seed_opps(["FIT-E"])
    rows = _rows(["FIT-E"])
    _apply_fit(db, _user(), rows, LIFECYCLE)  # must not raise
    assert rows[0]["fit_score"] is not None, "search must never break on scoring"
    assert rows[0]["fit_source"] == "estimate"


def test_estimates_are_per_user(db, client, auth_headers, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(
        gateway, "prescreen_scores", lambda p, r: {row["id"]: 50.0 for row in r}
    )
    _seed_opps(["FIT-F", "FIT-F2"])
    user_a = _user()
    rows = _rows(["FIT-F", "FIT-F2"])
    _apply_fit(db, user_a, rows, LIFECYCLE)

    db2 = SessionLocal()
    try:
        other = db2.query(User).filter(User.email != user_a.email).first()
        if other is None:
            other = User(email="fit-other@rackner.com")
            db2.add(other)
            db2.commit()
            db2.refresh(other)
        mine = db2.query(FitEstimate).filter_by(user_id=user_a.id, opportunity_id="FIT-F").count()
        theirs = db2.query(FitEstimate).filter_by(user_id=other.id, opportunity_id="FIT-F").count()
    finally:
        db2.close()
    assert mine == 1 and theirs == 0


def test_single_row_pages_skip_the_model(db, client, auth_headers, monkeypatch):
    """A detail view (one row) must never fire a model call per click — the
    heuristic is instant, and the analysis pre-warm supersedes it anyway."""
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    calls = {"n": 0}

    def counting(profile, rows):
        calls["n"] += 1
        return {}

    monkeypatch.setattr(gateway, "prescreen_scores", counting)
    _seed_opps(["FIT-H"])
    rows = _rows(["FIT-H"])
    _apply_fit(db, _user(), rows, LIFECYCLE)
    assert calls["n"] == 0, "single-row batches stay off the model"
    assert rows[0]["fit_score"] is not None and rows[0]["fit_source"] == "estimate"


def test_prescreen_row_cap_bounds_one_call(monkeypatch):
    """Past the cap, the batch is sliced (logged) so the response can't
    truncate and search latency stays bounded; the caller's heuristic covers
    the rest."""
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(config, "FIT_PRESCREEN_MAX_ROWS", 10)
    seen = {}
    from app.llm import bedrock_client

    def fake_invoke(system, prompt, max_tokens=None, profile="default"):
        seen["prompt"] = prompt
        seen["profile"] = profile
        return "[]"

    monkeypatch.setattr(bedrock_client, "invoke", fake_invoke)
    gateway.prescreen_scores(LIFECYCLE, [{"id": f"R{i}"} for i in range(30)])
    assert seen["profile"] == "interactive", "search must use the fail-fast client"
    assert seen["prompt"].count('"id"') == 10, "batch sliced to the cap"


# --- gateway parsing -----------------------------------------------------------


def test_prescreen_parsing_clamps_and_drops(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    from app.llm import bedrock_client

    monkeypatch.setattr(
        bedrock_client,
        "invoke",
        lambda system, prompt, max_tokens=None, profile="default": (
            '[{"id": "X", "score": 140}, {"id": "Y", "score": -5},'
            ' {"id": "INVENTED", "score": 50}, {"id": "Z", "score": "high"}]'
        ),
    )
    out = gateway.prescreen_scores(
        LIFECYCLE, [{"id": "X"}, {"id": "Y"}, {"id": "Z"}]
    )
    assert out == {"X": 100.0, "Y": 0.0}, "clamped; invented ids and junk dropped"


def test_prescreen_noop_in_mock_mode(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "mock")
    assert gateway.prescreen_scores(LIFECYCLE, [{"id": "X"}]) == {}


# --- plan changes --------------------------------------------------------------


def test_new_plan_invalidates_cached_estimates(client, auth_headers):
    _seed_opps(["FIT-G"])
    user = _user()
    db = SessionLocal()
    try:
        db.add(FitEstimate(user_id=user.id, opportunity_id="FIT-G", score=42.0))
        db.commit()
    finally:
        db.close()

    plan = (
        b"Capabilities: cybersecurity, cloud migration\n"
        b"NAICS: 541512\nTarget agencies: DoD\n"
    )
    r = client.post(
        "/profile/lifecycle",
        headers=auth_headers,
        files={"file": ("plan.txt", io.BytesIO(plan), "text/plain")},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        remaining = db.query(FitEstimate).filter_by(user_id=user.id).count()
    finally:
        db.close()
    assert remaining == 0, "estimates scored against the old plan must die"
