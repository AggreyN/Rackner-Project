"""Week-3 routes over HTTP, with the upstreams stubbed.

Deliberately offline: CI must not depend on SAM.gov or USAspending being up,
and the point of these tests is our behaviour, not theirs. The live smoke test
lives in test_live_gov_apis.py behind an opt-in flag.

The fail-soft cases get as much attention as the happy path, because ground
rule 8 is where this week's bugs will be: an upstream outage must produce a
503 that names the service, never an empty list (which the UI would render as
"nothing exists") and never a 500.
"""

from __future__ import annotations

import pytest

from app.services import samgov, usaspending
from app.services.http import UpstreamError

SAM_SUMMARY = {
    "id": "SAM-1",
    "title": "Continuous Monitoring Support",
    "agency": "Dept Of Defense",
    "office": "DISA",
    "solicitation_number": "HC1084-26-R-0042",
    "naics": "541512",
    "set_aside": "HUBZone",
    "kind": "solicitation",
    "description": "The Contractor shall provide continuous monitoring.",
    "close_date": "2026-12-31",
    "days_to_close": 150,
    "est_value": None,
    "incumbent": None,
    "fit_score": None,
    "expiry_date": None,
    "months_to_expiry": None,
    "current_award_value": None,
    "_source_url": "https://sam.gov/opp/SAM-1",
    "_description_url": "https://api.sam.gov/desc?id=SAM-1",
    "_point_of_contact": [
        {"type": "primary", "email": "jane.doe@army.mil", "fullName": "Jane Doe (Contracting Officer)"}
    ],
}

AWARD_SUMMARY = {
    "id": "AWD-1",
    "title": "MANAGED CARE SUPPORT",
    "agency": "Department of Defense",
    "office": "Defense Health Agency",
    "solicitation_number": "HT940216C0001",
    "naics": "524114",
    "set_aside": None,
    "kind": "expiring_award",
    "description": "Managed care support services.",
    "close_date": None,
    "days_to_close": None,
    "est_value": "$51.3B",
    "incumbent": "HUMANA GOVERNMENT BUSINESS INC",
    "fit_score": None,
    "expiry_date": "2027-09-30",
    "months_to_expiry": 14,
    "current_award_value": 51269205263.03,
    "_source_url": "https://www.usaspending.gov/award/AWD-1",
    "_description_url": "",
    "_point_of_contact": [],
}


@pytest.fixture
def stub_upstreams(monkeypatch):
    monkeypatch.setattr(samgov, "search", lambda *a, **k: [dict(SAM_SUMMARY)])
    monkeypatch.setattr(samgov, "get_opportunity", lambda *a, **k: dict(SAM_SUMMARY))
    monkeypatch.setattr(samgov, "fetch_description", lambda *a, **k: SAM_SUMMARY["description"])
    monkeypatch.setattr(samgov, "is_configured", lambda: True)
    monkeypatch.setattr(usaspending, "expiring_awards", lambda *a, **k: [dict(AWARD_SUMMARY)])


@pytest.fixture
def down_upstreams(monkeypatch):
    def boom(*a, **k):
        raise UpstreamError("SAM.gov", "timeout after (5, 30)s")

    def boom_usa(*a, **k):
        raise UpstreamError("USAspending.gov", "HTTP 502")

    monkeypatch.setattr(samgov, "search", boom)
    monkeypatch.setattr(samgov, "get_opportunity", boom)
    monkeypatch.setattr(usaspending, "expiring_awards", boom_usa)
    monkeypatch.setattr(usaspending, "spend_summary", boom_usa)


# --- search -------------------------------------------------------------------


def test_search_requires_auth(client):
    assert client.get("/opportunities/search?q=cyber").status_code == 401


def test_search_returns_both_kinds(client, auth_headers, stub_upstreams):
    r = client.get("/opportunities/search?q=monitoring", headers=auth_headers)
    assert r.status_code == 200, r.text
    kinds = {o["kind"] for o in r.json()}
    assert kinds == {"solicitation", "expiring_award"}


def test_search_results_match_the_contract_shape(client, auth_headers, stub_upstreams):
    from app.schemas import OpportunitySummary

    body = client.get("/opportunities/search?q=x", headers=auth_headers).json()
    expected = set(OpportunitySummary.model_fields)
    for row in body:
        assert set(row) == expected
        assert not any(k.startswith("_") for k in row), "internal keys leaked to the wire"


def test_search_caches_results_so_detail_works_afterwards(client, auth_headers, stub_upstreams):
    """This is what makes /analysis and /document reachable at all."""
    client.get("/opportunities/search?q=x", headers=auth_headers)
    r = client.get("/opportunities/SAM-1/document", headers=auth_headers)
    assert r.status_code == 200, r.text


def test_kinds_filter_selects_only_expiring_awards(client, auth_headers, stub_upstreams):
    r = client.get("/opportunities/search?kinds=expiring_award", headers=auth_headers)
    assert {o["kind"] for o in r.json()} == {"expiring_award"}


def test_kinds_filter_selects_only_solicitations(client, auth_headers, stub_upstreams):
    r = client.get("/opportunities/search?kinds=solicitation", headers=auth_headers)
    assert {o["kind"] for o in r.json()} == {"solicitation"}


def test_expiring_window_is_passed_through(client, auth_headers, monkeypatch):
    """The recompete window must be applied server-side, per the contract."""
    seen = {}

    def capture(*, from_months, to_months, limit, **kw):
        seen["from"], seen["to"] = from_months, to_months
        return []

    monkeypatch.setattr(usaspending, "expiring_awards", capture)
    monkeypatch.setattr(samgov, "search", lambda *a, **k: [])
    client.get(
        "/opportunities/search?kinds=expiring_award&expiring_from=12&expiring_to=18",
        headers=auth_headers,
    )
    assert (seen["from"], seen["to"]) == (12, 18)


# --- suggested ----------------------------------------------------------------


def test_suggested_ranks_by_fit(client, auth_headers, stub_upstreams):
    r = client.get("/opportunities/suggested", headers=auth_headers)
    assert r.status_code == 200, r.text
    scores = [o["fit_score"] for o in r.json()]
    assert scores == sorted(scores, key=lambda s: s or 0, reverse=True)


def test_suggested_works_for_a_user_with_no_plan(client, credentials, stub_upstreams):
    """A new user should still see the market, unranked."""
    creds = {"email": "noplan@rackner.com", "password": "noplan-password-123"}
    client.post("/auth/register", json=creds)
    token = client.post("/auth/login", json=creds).json()["access_token"]
    r = client.get("/opportunities/suggested", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert all(o["fit_score"] is None for o in r.json())


# --- detail -------------------------------------------------------------------


def test_get_opportunity_by_id(client, auth_headers, stub_upstreams):
    r = client.get("/opportunities/SAM-1", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "SAM-1"


def test_search_path_is_not_matched_as_an_id(client, auth_headers, stub_upstreams):
    """Route order: /opportunities/search must not resolve to /opportunities/{id}."""
    r = client.get("/opportunities/search", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# --- fail soft (ground rule 8) ------------------------------------------------


def test_search_returns_503_not_empty_when_sam_is_down(client, auth_headers, down_upstreams):
    """An empty 200 would read as 'no opportunities exist'. It must be a 503."""
    r = client.get("/opportunities/search?q=cyber", headers=auth_headers)
    assert r.status_code == 503
    assert "SAM.gov" in r.json()["detail"]


def test_503_names_the_failing_service(client, auth_headers, down_upstreams):
    r = client.get("/opportunities/search?kinds=expiring_award", headers=auth_headers)
    assert r.status_code == 503
    assert "USAspending" in r.json()["detail"]


def test_detail_serves_stale_cache_when_sam_is_down(client, auth_headers, stub_upstreams, monkeypatch):
    """Once cached, an outage must not take the opportunity away."""
    client.get("/opportunities/SAM-1", headers=auth_headers)  # populate

    def boom(*a, **k):
        raise UpstreamError("SAM.gov", "timeout")

    monkeypatch.setattr(samgov, "get_opportunity", boom)
    r = client.get("/opportunities/SAM-1", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == "SAM-1"


def test_spend_returns_503_when_usaspending_is_down(client, auth_headers, stub_upstreams, down_upstreams):
    client.get("/opportunities/search?q=x", headers=auth_headers)
    r = client.get("/opportunities/SAM-1/spend", headers=auth_headers)
    assert r.status_code == 503


# --- spend --------------------------------------------------------------------


def test_spend_shape(client, auth_headers, stub_upstreams, monkeypatch):
    monkeypatch.setattr(
        usaspending,
        "spend_summary",
        lambda **kw: {
            "opportunity_id": kw["opportunity_id"],
            "years": [{"fiscal_year": "FY25", "amount": 1000.0}],
            "total_obligated": 1000.0,
            "incumbent": {"name": "ACME", "uei": ""},
            "trend_pct": 12.5,
        },
    )
    client.get("/opportunities/search?q=x", headers=auth_headers)
    r = client.get("/opportunities/SAM-1/spend", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"opportunity_id", "years", "total_obligated", "incumbent", "trend_pct"}
    assert set(body["years"][0]) == {"fiscal_year", "amount"}


def test_spend_404_for_unknown_opportunity(client, auth_headers):
    assert client.get("/opportunities/NOPE/spend", headers=auth_headers).status_code == 404


# --- contact ------------------------------------------------------------------


def test_contact_shape_and_published_address(client, auth_headers, stub_upstreams):
    client.get("/opportunities/search?q=x", headers=auth_headers)
    r = client.get("/opportunities/SAM-1/contact", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "opportunity_id", "name", "title", "office", "email", "confidence", "active_solicitation",
    }
    assert body["email"] == "jane.doe@army.mil"
    assert body["active_solicitation"] is True


def test_contact_404_when_nothing_can_be_identified(client, auth_headers, stub_upstreams, monkeypatch):
    """A fabricated address is worse than none."""
    monkeypatch.setattr(usaspending, "expiring_awards", lambda *a, **k: [dict(AWARD_SUMMARY)])
    client.get("/opportunities/search?kinds=expiring_award", headers=auth_headers)
    r = client.get("/opportunities/AWD-1/contact", headers=auth_headers)
    assert r.status_code == 404


# --- chat ---------------------------------------------------------------------


def test_chat_shape_and_grounding(client, auth_headers, stub_upstreams):
    client.get("/opportunities/search?q=x", headers=auth_headers)
    r = client.post(
        "/opportunities/SAM-1/chat",
        headers=auth_headers,
        json={"question": "What continuous monitoring is required?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"answer", "citations"}
    assert all(set(c) == {"section", "page"} for c in body["citations"])


def test_chat_citations_reference_real_sections(client, auth_headers, stub_upstreams):
    client.get("/opportunities/search?q=x", headers=auth_headers)
    doc = client.get("/opportunities/SAM-1/document", headers=auth_headers).json()
    refs = {s["ref"] for s in doc["sections"]}
    body = client.post(
        "/opportunities/SAM-1/chat",
        headers=auth_headers,
        json={"question": "What continuous monitoring is required?"},
    ).json()
    for citation in body["citations"]:
        assert citation["section"] in refs


def test_chat_admits_when_the_source_does_not_answer(client, auth_headers, stub_upstreams):
    """No citations rather than a confident answer from general knowledge."""
    client.get("/opportunities/search?q=x", headers=auth_headers)
    body = client.post(
        "/opportunities/SAM-1/chat",
        headers=auth_headers,
        json={"question": "What is the airspeed velocity of an unladen swallow?"},
    ).json()
    assert body["citations"] == []


def test_chat_rejects_an_empty_question(client, auth_headers, stub_upstreams):
    client.get("/opportunities/search?q=x", headers=auth_headers)
    r = client.post("/opportunities/SAM-1/chat", headers=auth_headers, json={"question": "  "})
    assert r.status_code == 400


def test_chat_404_for_unknown_opportunity(client, auth_headers):
    r = client.post("/opportunities/NOPE/chat", headers=auth_headers, json={"question": "hi"})
    assert r.status_code == 404


def test_gateway_drops_citations_to_sections_that_do_not_exist(monkeypatch):
    """A model that invents a section ref must not produce a dangling citation."""
    from app import config
    from app.llm import gateway, mock

    monkeypatch.setattr(config, "LLM_MODE", "mock")
    monkeypatch.setattr(
        mock,
        "answer_question",
        lambda q, s: {"answer": "x", "citations": [{"section": "Z.9.9", "page": 1}]},
    )
    result = gateway.answer_question("q", [{"ref": "C.1", "page": 1, "text": "text"}])
    assert result["citations"] == []
    assert result["answer"] == "x", "the answer text is kept even when a citation is dropped"
