"""Generation hardening — the four fixes from the 2026-08-11 prod incident.

A 60-section package took minutes to extract sequentially, outlived the load
balancer, and every timed-out retry started a DUPLICATE full generation until
the task wedged. The fixes under test:
  1. per-section extraction runs concurrently in bedrock mode, output
     byte-identical to the sequential path;
  2. a request that finds generation in flight waits, then returns 503 +
     Retry-After — it never starts a duplicate run;
  3. section refs are unique (real packages repeat clause numbers, which
     broke ref-keyed citation lookup);
  4. one analysis per (opportunity, user), DB-enforced, with the losing
     concurrent persist serving the winner.
"""

from __future__ import annotations

import threading
import time

import pytest

from app import config
from app.database import SessionLocal
from app.llm import gateway
from app.models import Analysis, Opportunity, User
from app.services import ingest


def _sections(n: int) -> list[dict]:
    return [
        {
            "ref": f"C.{i}",
            "page": 1,
            "text": f"Section {i}: The Contractor shall perform task {i}.",
        }
        for i in range(1, n + 1)
    ]


def _raw_for(text: str) -> list[dict]:
    quote = text[: len(text) // 2]
    return [
        {
            "text": f"obligation from {text[:12]!r}",
            "obligation_type": "performance",
            "time_bucket": "ongoing",
            "deadline_label": "",
            "verbatim_quote": quote,
        }
    ]


# --- fix 1: parallel extraction --------------------------------------------------


def test_bedrock_extraction_runs_concurrently(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(config, "LLM_EXTRACT_CONCURRENCY", 8)

    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow_raw(text):
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.15)
        with lock:
            active["now"] -= 1
        return _raw_for(text)

    monkeypatch.setattr(gateway, "_raw_obligations_for", slow_raw)
    start = time.monotonic()
    out = gateway.extract_obligations(_sections(8))
    elapsed = time.monotonic() - start

    assert len(out) == 8
    assert active["max"] > 1, "calls must overlap"
    assert elapsed < 0.15 * 8 * 0.6, f"not concurrent: {elapsed:.2f}s for 8x0.15s"


def test_parallel_output_is_identical_to_sequential(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(gateway, "_raw_obligations_for", _raw_for)
    sections = _sections(6)

    monkeypatch.setattr(config, "LLM_EXTRACT_CONCURRENCY", 8)
    parallel_out = gateway.extract_obligations(sections)
    monkeypatch.setattr(config, "LLM_EXTRACT_CONCURRENCY", 1)
    sequential_out = gateway.extract_obligations(sections)

    assert parallel_out == sequential_out, "order and ids must be stable"
    assert [o["id"] for o in parallel_out] == list(range(1, 7))
    assert [o["citation"]["section"] for o in parallel_out] == [
        s["ref"] for s in sections
    ]


def test_persistently_failing_section_is_skipped_not_fatal(monkeypatch):
    """Measured in prod: all-or-nothing at 60 sections meant one throttled
    call vaporized the whole run. A section that fails its retry is skipped
    with a warning; everything else survives."""
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(config, "LLM_EXTRACT_CONCURRENCY", 4)

    def flaky(text):
        if "task 3" in text:
            raise RuntimeError("model exploded")
        return _raw_for(text)

    monkeypatch.setattr(gateway, "_raw_obligations_for", flaky)
    out = gateway.extract_obligations(_sections(5))
    assert len(out) == 4, "the other four sections must survive"
    assert "C.3" not in {o["citation"]["section"] for o in out}


def test_transient_failure_recovers_on_the_serial_retry(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(config, "LLM_EXTRACT_CONCURRENCY", 4)

    attempts = {"n": 0}

    def throttled_once(text):
        if "task 2" in text:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("ThrottlingException")
        return _raw_for(text)

    monkeypatch.setattr(gateway, "_raw_obligations_for", throttled_once)
    out = gateway.extract_obligations(_sections(4))
    assert len(out) == 4, "the retried section must be recovered"
    assert [o["id"] for o in out] == [1, 2, 3, 4], "ids stay stable after retry"


def test_total_outage_still_raises(monkeypatch):
    """Every section failing means Bedrock is down — raising beats persisting
    a frozen, empty analysis."""
    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(config, "LLM_EXTRACT_CONCURRENCY", 4)

    def dead(text):
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(gateway, "_raw_obligations_for", dead)
    with pytest.raises(RuntimeError):
        gateway.extract_obligations(_sections(3))


# --- fix 2: stampede guard --------------------------------------------------------


@pytest.fixture()
def guard_opp(client, auth_headers):
    opp_id = "STAMPEDE-1"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id) or Opportunity(
            id=opp_id, title="Stampede target", agency="DoD"
        )
        db.add(row)
        row.description = "The Contractor shall not be stampeded."
        db.query(Analysis).filter_by(opportunity_id=opp_id).delete()
        db.commit()
    finally:
        db.close()
    return opp_id


def test_held_guard_returns_503_with_retry_after_not_a_duplicate_run(
    client, auth_headers, guard_opp, monkeypatch
):
    from app.routes import analysis as analysis_module

    calls = {"generations": 0}
    real_generate = analysis_module._generate_and_store

    def counting_generate(*a, **kw):
        calls["generations"] += 1
        return real_generate(*a, **kw)

    monkeypatch.setattr(analysis_module, "_generate_and_store", counting_generate)
    # Skip the real 45s wait; the holder "never finishes" in this test.
    monkeypatch.setattr(
        analysis_module, "_wait_for_inflight", lambda *a, **kw: None
    )

    me = client.get("/me", headers=auth_headers).json()
    assert analysis_module._acquire(me["id"], guard_opp)
    try:
        r = client.get(f"/opportunities/{guard_opp}/analysis", headers=auth_headers)
        assert r.status_code == 503
        assert r.headers.get("retry-after"), "clients need to know to come back"
        assert calls["generations"] == 0, "a held guard must NEVER duplicate-generate"
    finally:
        analysis_module._release(me["id"], guard_opp)

    # Guard released -> the same request now generates normally.
    r = client.get(f"/opportunities/{guard_opp}/analysis", headers=auth_headers)
    assert r.status_code == 200
    assert calls["generations"] == 1


# --- fix 3: unique section refs ---------------------------------------------------


def test_repeated_clause_numbers_get_unique_refs():
    raw = (
        "52.212-4 CONTRACT TERMS AND CONDITIONS\n"
        "The base clause text.\n"
        "52.212-4 CONTRACT TERMS AND CONDITIONS (ALTERNATE I)\n"
        "The alternate clause text.\n"
        "52.212-4 ADDENDUM\n"
        "The addendum text.\n"
    )
    sections = ingest.split_sections(raw)
    refs = [s["ref"] for s in sections]
    assert len(refs) == len(set(refs)), f"refs must be unique: {refs}"
    assert "".join(s["text"] for s in sections) == raw, "still lossless"


def test_ref_lookup_lands_on_the_right_text():
    raw = (
        "52.212-4 FIRST\nalpha body\n"
        "52.212-4 SECOND\nbravo body\n"
    )
    sections = ingest.split_sections(raw)
    by_ref = {s["ref"]: s["text"] for s in sections}
    assert len(by_ref) == len(sections), "no ref may shadow another"
    assert "alpha body" in by_ref["52.212-4"]
    assert "bravo body" in by_ref["52.212-4 #2"]


# --- fix 4: analyses uniqueness ---------------------------------------------------


def test_duplicate_analysis_rows_are_db_rejected(guard_opp):
    from sqlalchemy.exc import IntegrityError

    db = SessionLocal()
    try:
        user = db.query(User).first()
        for verdict in ("first", "second"):
            db.add(
                Analysis(
                    opportunity_id=guard_opp,
                    user_id=user.id,
                    score=10.0,
                    band="no_bid",
                    verdict=verdict,
                    factors=[],
                    obligations=[],
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_losing_a_persist_race_serves_the_winner(client, auth_headers, guard_opp, monkeypatch):
    """A competing generation commits mid-model-call; our persist must catch
    the unique violation and serve the winner's row, not 500."""
    me = client.get("/me", headers=auth_headers).json()
    real_analyze = gateway.analyze

    def analyze_and_lose(opp_dict, profile, sections):
        result = real_analyze(opp_dict, profile, sections)
        db = SessionLocal()
        try:
            db.add(
                Analysis(
                    opportunity_id=guard_opp,
                    user_id=me["id"],
                    score=99.0,
                    band="pursue",
                    verdict="the winner",
                    factors=[],
                    obligations=[],
                )
            )
            db.commit()
        finally:
            db.close()
        return result

    monkeypatch.setattr(gateway, "analyze", analyze_and_lose)
    r = client.get(f"/opportunities/{guard_opp}/analysis", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] == "the winner"

    db = SessionLocal()
    try:
        count = db.query(Analysis).filter_by(opportunity_id=guard_opp).count()
    finally:
        db.close()
    assert count == 1