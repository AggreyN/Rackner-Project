"""Live Bedrock tests — opt-in, because they cost money and need credentials.

    RUN_BEDROCK_TESTS=1 AWS_BEARER_TOKEN_BEDROCK=... pytest tests/test_bedrock_live.py

Skipped by default so CI stays free and offline. These cover the one thing mock
mode structurally cannot: whether the REAL model's output survives the gateway.

Measured behaviour on 2026-08-03, claude-sonnet-4-5, us-east-2:
  * synthetic solicitation -> 4/4 quotes character-exact, all verified
  * real federal PDF       -> 4/8 verified; the misses were quotes spanning
                              form-field line breaks, which the model re-wrapped

That second number is the point. The model DOES drift on whitespace-heavy text,
and the system handles it correctly: drifted quotes come back verified=False
rather than being falsely marked verified. These tests assert that property —
NOT a verification rate, which would be flaky against a live model.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BEDROCK_TESTS") != "1",
    reason="live Bedrock test; set RUN_BEDROCK_TESTS=1 (costs money)",
)

SOLICITATION = """SECTION C — DESCRIPTION / SPECIFICATIONS
The Contractor shall provide continuous monitoring of all information systems.

C.3.1 Incident Reporting
The Contractor shall report any cyber incident to the Contracting Officer within 72 hours of discovery.

252.204-7012 Safeguarding Covered Defense Information
The Contractor shall deliver a monthly status report summarizing all safeguarding activities."""


@pytest.fixture(scope="module")
def bedrock_mode(monkeypatch_session=None):
    """Force the gateway onto the real path for this module."""
    from app import config

    original = config.LLM_MODE
    config.LLM_MODE = "bedrock"
    yield
    config.LLM_MODE = original


@pytest.fixture(scope="module")
def sections():
    from app.services import ingest

    return ingest.split_sections(SOLICITATION)


def test_real_model_returns_parseable_obligations(bedrock_mode, sections):
    from app.llm import gateway

    obs = gateway.extract_obligations(sections)
    assert obs, "the real model returned nothing the gateway could parse"
    for o in obs:
        assert set(o) >= {"id", "text", "verbatim_quote", "citation", "verified"}


def test_real_model_quotes_that_verify_are_exact(bedrock_mode, sections):
    """The invariant, against a live model: verified => exact substring.

    Deliberately does NOT assert a verification rate. The model drifts on
    whitespace-heavy source text; what must never happen is a drifted quote
    being marked verified.
    """
    from app.llm import gateway

    by_ref = {s["ref"]: s["text"] for s in sections}
    for o in gateway.extract_obligations(sections):
        if o["verified"]:
            cited = by_ref.get(o["citation"]["section"])
            assert cited is not None, f"citation names an unknown section: {o['citation']}"
            assert o["verbatim_quote"] in cited, (
                "a live-model quote was marked verified but is not an exact "
                f"substring of its cited section: {o['verbatim_quote'][:90]!r}"
            )


def test_real_model_citations_name_real_sections(bedrock_mode, sections):
    from app.llm import gateway

    refs = {s["ref"] for s in sections}
    for o in gateway.extract_obligations(sections):
        assert o["citation"]["section"] in refs


def test_real_analyze_returns_the_eight_factors(bedrock_mode, sections):
    from app.llm import gateway

    opp = {
        "id": "LIVE-001",
        "title": "Continuous Monitoring Support",
        "agency": "DoD · DISA",
        "naics": "541512",
        "set_aside": "HUBZone",
        "description": SOLICITATION,
        "close_date": "2026-09-30",
        "est_value": "$8-12M / 5yr",
    }
    profile = {
        "capabilities": ["cloud security", "continuous monitoring"],
        "naics_codes": ["541512"],
        "target_agencies": ["DoD"],
        "set_asides": ["HUBZone"],
        "past_performance": ["DISA SOC support 2023-2025"],
        "contract_vehicles": ["GSA MAS"],
    }
    a = gateway.analyze(opp, profile, sections)

    assert set(a) == {"opportunity_id", "score", "band", "verdict", "factors", "obligations"}
    assert len(a["factors"]) == 8, f"expected 8 canonical factors, got {len(a['factors'])}"
    assert all(1 <= f["score"] <= 5 for f in a["factors"])
    assert abs(sum(f["weight"] for f in a["factors"]) - 1.0) < 1e-6
    assert all(f["rationale"].strip() for f in a["factors"]), "Kaliza's prompt requires a rationale"
    assert 0 <= a["score"] <= 100
    # The backend derives these — never the model.
    from app.schemas import band_for

    assert a["band"] == band_for(a["score"])
    assert a["verdict"] not in ("pursue", "conditional", "no_bid")


def test_real_model_cannot_self_certify_verification(bedrock_mode, sections):
    """Even if the model emits verified=true, the backend must overwrite it."""
    from app.llm import gateway

    for o in gateway.extract_obligations(sections):
        by_ref = {s["ref"]: s["text"] for s in sections}
        expected = o["verbatim_quote"] in by_ref.get(o["citation"]["section"], "")
        assert o["verified"] is expected
