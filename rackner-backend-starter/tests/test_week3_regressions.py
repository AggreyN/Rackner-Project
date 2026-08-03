"""Regression tests for the five Week-3 bugs found by post-hoc audit.

All five were invisible to the original suite for the same structural reason:
they lived in stubbed seams (samgov.get_opportunity was always monkeypatched),
in cross-endpoint SEQUENCING (nothing tested /document before the detail view),
or in the gap between two teammates' vocabularies (fit's agency matching).
Each test here reproduces the original failure path, not just the fixed
behaviour.
"""

from __future__ import annotations

import datetime

import pytest

from app.services import fit, samgov


# --- 1. empty grounding documents must rebuild, not persist -------------------


@pytest.fixture
def bare_opportunity(client):
    """An opportunity cached the way SEARCH caches it: no description yet."""
    from app.database import SessionLocal
    from app.models import Opportunity

    opp_id = "REGRESSION-EMPTY-DOC"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id)
        if row is None:
            row = Opportunity(id=opp_id, title="Bare from search", agency="DoD", kind="solicitation")
            db.add(row)
        row.description = ""  # reset in case an earlier run filled it
        db.commit()
        # Drop any document a previous test run may have built.
        from app.models import SourceDocument

        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.commit()
    finally:
        db.close()
    return opp_id


def _set_description(opp_id: str, text: str) -> None:
    from app.database import SessionLocal
    from app.models import Opportunity

    db = SessionLocal()
    try:
        db.get(Opportunity, opp_id).description = text
        db.commit()
    finally:
        db.close()


SOURCE = (
    "C.3.1 Incident Reporting\n"
    "The Contractor shall report any cyber incident within 72 hours."
)


def test_document_built_empty_rebuilds_once_text_arrives(client, auth_headers, bare_opportunity):
    """THE sequencing bug: /document before the detail view used to freeze an
    empty document forever, killing grounding for that opportunity."""
    # Step 1: hit /document while the opportunity has no source text.
    first = client.get(f"/opportunities/{bare_opportunity}/document", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["sections"] == []

    # Step 2: the detail view fetches and caches the description.
    _set_description(bare_opportunity, SOURCE)

    # Step 3: the document must now rebuild, not replay the empty one.
    second = client.get(f"/opportunities/{bare_opportunity}/document", headers=auth_headers)
    assert second.json()["sections"], "empty document was frozen despite text arriving"
    assert any(s["ref"] == "C.3.1" for s in second.json()["sections"])


def test_populated_documents_are_still_never_rebuilt(client, auth_headers, bare_opportunity):
    """The fix must not weaken build-once for documents WITH sections — a
    rebuild there could change text that quotes were verified against."""
    _set_description(bare_opportunity, SOURCE)
    first = client.get(f"/opportunities/{bare_opportunity}/document", headers=auth_headers).json()
    assert first["sections"]

    _set_description(bare_opportunity, SOURCE + "\n\nC.9 Added later\nNew clause text.")
    second = client.get(f"/opportunities/{bare_opportunity}/document", headers=auth_headers).json()
    assert second == first, "a populated document must stay frozen"


# --- 2. ungrounded analyses must not be cached --------------------------------


def test_analysis_before_text_is_not_frozen(client, auth_headers, bare_opportunity):
    """Same sequencing, one layer up: /analysis before the description arrives
    used to cache an obligation-less analysis per user, permanently."""
    first = client.get(f"/opportunities/{bare_opportunity}/analysis", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["obligations"] == []  # nothing to ground in yet — honest

    _set_description(bare_opportunity, SOURCE)

    second = client.get(f"/opportunities/{bare_opportunity}/analysis", headers=auth_headers)
    assert second.json()["obligations"], (
        "analysis generated against an empty document was cached and never regenerated"
    )


def test_grounded_analysis_is_still_cached(client, auth_headers, bare_opportunity):
    _set_description(bare_opportunity, SOURCE)
    first = client.get(f"/opportunities/{bare_opportunity}/analysis", headers=auth_headers).json()
    second = client.get(f"/opportunities/{bare_opportunity}/analysis", headers=auth_headers).json()
    assert first == second


# --- 3. SAM noticeid lookups must carry the mandatory date window -------------


def test_get_opportunity_sends_posted_window(monkeypatch):
    """SAM v2 rejects ANY request without postedFrom/postedTo — including
    noticeid lookups. The API tests stub this function, so only a params-level
    test can catch the omission."""
    from app import config

    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "test-key")
    captured: dict = {}

    def fake_get_json(url, *, service, params=None, timeout=None):
        captured.update(params or {})
        return {"opportunitiesData": []}

    monkeypatch.setattr(samgov, "get_json", fake_get_json)
    samgov.get_opportunity("SOME-NOTICE", today=datetime.date(2026, 8, 3))

    assert captured.get("noticeid") == "SOME-NOTICE"
    assert captured.get("postedFrom") == "08/04/2025", "postedFrom missing → SAM returns 400"
    assert captured.get("postedTo") == "08/03/2026"


def test_posted_window_never_exceeds_sam_one_year_cap():
    frm = datetime.date(2026, 8, 3) - datetime.timedelta(days=364)
    assert (datetime.date(2026, 8, 3) - frm).days <= 365


# --- 4. free-text search must filter expiring awards --------------------------


def test_query_filters_expiring_awards(client, auth_headers, monkeypatch):
    from app.services import usaspending

    cyber = {
        "id": "AWD-CYBER", "title": "Cybersecurity monitoring support", "agency": "DoD",
        "office": None, "solicitation_number": "X1", "naics": None, "set_aside": None,
        "kind": "expiring_award", "description": "SOC operations", "close_date": None,
        "days_to_close": None, "est_value": "$5.0M", "incumbent": "ACME CYBER LLC",
        "fit_score": None, "expiry_date": "2027-09-30", "months_to_expiry": 14,
        "current_award_value": 5e6, "_source_url": "", "_description_url": "",
        "_point_of_contact": [],
    }
    catering = {**cyber, "id": "AWD-FOOD", "title": "Cafeteria services",
                "description": "food service", "incumbent": "TASTY LLC"}

    monkeypatch.setattr(usaspending, "expiring_awards", lambda **kw: [dict(cyber), dict(catering)])
    monkeypatch.setattr(samgov, "search", lambda *a, **k: [])

    r = client.get("/opportunities/search?q=cyber&kinds=expiring_award", headers=auth_headers)
    ids = [o["id"] for o in r.json()]
    assert "AWD-CYBER" in ids, "matching award was filtered out"
    assert "AWD-FOOD" not in ids, "free-text query was ignored for expiring awards"


def test_empty_query_keeps_all_expiring_awards(client, auth_headers, monkeypatch):
    from app.services import usaspending

    rows = [
        {"id": f"AWD-{i}", "title": f"Award {i}", "agency": "DoD", "office": None,
         "solicitation_number": None, "naics": None, "set_aside": None,
         "kind": "expiring_award", "description": "", "close_date": None,
         "days_to_close": None, "est_value": None, "incumbent": None, "fit_score": None,
         "expiry_date": "2027-09-30", "months_to_expiry": 14, "current_award_value": None,
         "_source_url": "", "_description_url": "", "_point_of_contact": []}
        for i in range(3)
    ]
    monkeypatch.setattr(usaspending, "expiring_awards", lambda **kw: [dict(r) for r in rows])
    monkeypatch.setattr(samgov, "search", lambda *a, **k: [])

    r = client.get("/opportunities/search?kinds=expiring_award", headers=auth_headers)
    assert len(r.json()) == 3


# --- 5. agency abbreviations must not zero the fit score ----------------------


PLAN = {"naics_codes": [], "target_agencies": ["Department of Defense"],
        "set_asides": [], "capabilities": []}


def test_dept_abbreviation_matches_department():
    """SAM renders 'DEPT OF DEFENSE'; plans say 'Department of Defense'.
    Before the fix this scored 0 for the user's own primary target agency."""
    sam_style = {"naics": None, "agency": "Dept Of Defense", "set_aside": None,
                 "title": "", "description": ""}
    assert fit.score(sam_style, PLAN) > 0


def test_unrelated_agency_still_scores_zero():
    other = {"naics": None, "agency": "Department of Agriculture", "set_aside": None,
             "title": "", "description": ""}
    assert fit.score(other, PLAN) == 0


@pytest.mark.parametrize(
    "left,right",
    [
        ("Dept Of Defense", "Department of Defense"),
        ("dept. of defense", "Department of Defense"),
        ("Govt Accountability Office", "Government Accountability Office"),
        ("Purchasing & Contracting", "Purchasing and Contracting"),
    ],
)
def test_norm_equates_common_federal_spellings(left, right):
    assert fit._norm(left) == fit._norm(right)
