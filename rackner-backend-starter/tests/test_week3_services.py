"""Week-3 service logic: mapping, ranking, contacts, fail-soft.

No network. The upstream payloads below are trimmed copies of REAL responses
captured from SAM.gov and USAspending, so the field names under test are the
ones the services actually meet — several differ from what the build spec said
(`responseDeadLine` with a capital L; `End Date`, not "Period of Performance
Current End Date"; `description` is a URL, not text).
"""

from __future__ import annotations

import datetime

import pytest

from app.services import email_discovery, fit, samgov, usaspending
from app.services.http import UpstreamError

TODAY = datetime.date(2026, 8, 3)

# --- real SAM.gov record (trimmed) -------------------------------------------
SAM_RECORD = {
    "noticeId": "ffef05499c1143b5910147cd82afc0bd",
    "title": "Request for Quotes: Purchase of Professional Instruments",
    "solicitationNumber": "W912LR26QA037",
    "fullParentPathName": "DEPT OF DEFENSE.DEPT OF THE ARMY.NATIONAL GUARD BUREAU.USPFO PR PROCUREMENT",
    "naicsCode": "459140",
    "type": "Solicitation",
    "typeOfSetAside": "SBA",
    "typeOfSetAsideDescription": "Small Business Set Aside - Total",
    "responseDeadLine": "2026-08-14T14:00:00-04:00",
    "description": "https://api.sam.gov/prod/opportunities/v1/noticedesc?noticeid=ffef",
    "uiLink": "https://sam.gov/workspace/contract/opp/ffef/view",
    "pointOfContact": [
        {
            "type": "primary",
            "email": "argenies.e.gonzalezgarcia.mil@army.mil",
            "fullName": "Argenies Gonzalez (Contracting Officer)",
        },
        {
            "type": "secondary",
            "email": "ng.prarng.purchasing.mbx@army.mil",
            "fullName": "USPFO PR Purchasing & Contracting Mailbox",
        },
    ],
}

# --- real USAspending row (trimmed) ------------------------------------------
USA_ROW = {
    "Award ID": "HT940216C0001",
    "Recipient Name": "HUMANA GOVERNMENT BUSINESS INC",
    "Recipient UEI": "ABC123",
    "Awarding Agency": "Department of Defense",
    "Awarding Sub Agency": "Defense Health Agency",
    "End Date": "2027-09-30",
    "Award Amount": 51269205263.03,
    "Description": "MANAGED CARE SUPPORT CONTRACT",
    "naics_code": {"code": "524114", "description": "DIRECT HEALTH INSURANCE"},
    "generated_internal_id": "CONT_AWD_HT940216C0001_9700",
}


# --- SAM mapping --------------------------------------------------------------


def test_sam_record_maps_to_schema_v2():
    s = samgov.to_summary(SAM_RECORD, today=TODAY)
    assert s["id"] == "ffef05499c1143b5910147cd82afc0bd"
    assert s["kind"] == "solicitation"
    assert s["naics"] == "459140"
    assert s["set_aside"] == "Small Business Set Aside - Total"
    assert s["solicitation_number"] == "W912LR26QA037"


def test_sam_agency_and_office_split_from_dotted_path():
    s = samgov.to_summary(SAM_RECORD, today=TODAY)
    assert s["agency"] == "Dept Of Defense"
    assert s["office"] == "Uspfo Pr Procurement"


def test_sam_deadline_uses_the_capital_l_field():
    """responseDeadLine, not responseDeadline. Getting this wrong yields nulls."""
    s = samgov.to_summary(SAM_RECORD, today=TODAY)
    assert s["close_date"] == "2026-08-14"
    assert s["days_to_close"] == 11


def test_solicitations_have_null_recompete_fields():
    s = samgov.to_summary(SAM_RECORD, today=TODAY)
    assert s["expiry_date"] is None
    assert s["months_to_expiry"] is None
    assert s["current_award_value"] is None


def test_sam_has_no_dollar_value():
    """SAM.gov exposes none, so est_value must be null rather than invented."""
    assert samgov.to_summary(SAM_RECORD, today=TODAY)["est_value"] is None


def test_missing_deadline_is_tolerated():
    record = {**SAM_RECORD, "responseDeadLine": None}
    s = samgov.to_summary(record, today=TODAY)
    assert s["close_date"] is None and s["days_to_close"] is None


def test_unknown_type_falls_back_to_solicitation():
    assert samgov.to_summary({**SAM_RECORD, "type": "Wat"}, today=TODAY)["kind"] == "solicitation"


@pytest.mark.parametrize(
    "sam_type,expected",
    [
        ("Solicitation", "solicitation"),
        ("Presolicitation", "presolicitation"),
        ("Sources Sought", "sources_sought"),
        ("Special Notice", "baa"),
    ],
)
def test_kind_mapping(sam_type, expected):
    assert samgov.to_summary({**SAM_RECORD, "type": sam_type}, today=TODAY)["kind"] == expected


def test_html_description_becomes_text():
    html = "<p><strong>Update:</strong></p>\n<p>Amendment 0001 &amp; errata</p><li>item</li>"
    text = samgov.html_to_text(html)
    assert "<p>" not in text and "<strong>" not in text
    assert "&amp;" not in text and "&" in text
    assert "Amendment 0001" in text


def test_search_without_a_key_is_an_upstream_error(monkeypatch):
    """A missing key must be a clean 503 upstream, not a crash."""
    from app import config

    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "")
    with pytest.raises(UpstreamError):
        samgov.search("cyber")


# --- USAspending recompete radar ---------------------------------------------


def test_award_maps_to_expiring_award():
    s = usaspending._to_summary(USA_ROW, TODAY)
    assert s["kind"] == "expiring_award"
    assert s["expiry_date"] == "2027-09-30"
    assert s["incumbent"] == "HUMANA GOVERNMENT BUSINESS INC"
    assert s["current_award_value"] == pytest.approx(51269205263.03)
    assert s["naics"] == "524114"


def test_expiring_awards_have_no_close_date():
    """An expiring award is not open for response — SCHEMA_v2 requires null."""
    s = usaspending._to_summary(USA_ROW, TODAY)
    assert s["close_date"] is None and s["days_to_close"] is None


def test_months_to_expiry_is_computed():
    s = usaspending._to_summary(USA_ROW, TODAY)
    assert 13 <= s["months_to_expiry"] <= 14  # 2026-08-03 -> 2027-09-30


def test_absurd_end_dates_are_discarded():
    """USAspending really does contain end dates in 3017 and 2109."""
    assert usaspending._to_summary({**USA_ROW, "End Date": "3017-04-30"}, TODAY) is None
    assert usaspending._to_summary({**USA_ROW, "End Date": "2109-09-30"}, TODAY) is None


def test_missing_end_date_is_discarded():
    assert usaspending._to_summary({**USA_ROW, "End Date": None}, TODAY) is None


def test_est_value_is_a_display_string():
    """SCHEMA_v2: est_value is a STRING, unlike current_award_value."""
    assert usaspending._format_value(51269205263.03) == "$51.3B"
    assert usaspending._format_value(8_500_000) == "$8.5M"
    assert usaspending._format_value(2500) == "$2.5K"
    assert usaspending._format_value(0) is None
    assert usaspending._format_value(None) is None


def test_trend_needs_two_real_years():
    assert usaspending._trend_pct([]) is None
    assert usaspending._trend_pct([{"fiscal_year": "FY25", "amount": 10.0}]) is None
    trend = usaspending._trend_pct(
        [{"fiscal_year": "FY24", "amount": 100.0}, {"fiscal_year": "FY25", "amount": 124.0}]
    )
    assert trend == pytest.approx(24.0)


def test_spend_summary_without_an_incumbent_is_empty_not_invented():
    result = usaspending.spend_summary(opportunity_id="X", recipient=None)
    assert result["years"] == []
    assert result["total_obligated"] == 0.0
    assert result["incumbent"] is None
    assert result["trend_pct"] is None


# --- fit scoring --------------------------------------------------------------

PLAN = {
    "naics_codes": ["541512", "541519"],
    "target_agencies": ["Department of Defense"],
    "set_asides": ["HUBZone"],
    "capabilities": ["cloud security", "continuous monitoring"],
}


def test_no_plan_means_null_fit_score():
    assert fit.score({"naics": "541512"}, None) is None


def test_exact_naics_beats_partial_beats_none():
    exact = fit.score({"naics": "541512", "agency": "", "title": "", "description": ""}, PLAN)
    partial = fit.score({"naics": "541990", "agency": "", "title": "", "description": ""}, PLAN)
    none = fit.score({"naics": "111111", "agency": "", "title": "", "description": ""}, PLAN)
    assert exact > partial > none


def test_full_and_open_counts_as_eligible():
    """Unrestricted competition carries no eligibility risk."""
    assert fit.score({"set_aside": "Full and Open", "agency": "", "title": ""}, PLAN) > 0


def test_ranking_sorts_best_first():
    good = {"id": "a", "naics": "541512", "agency": "Department of Defense",
            "set_aside": "HUBZone", "title": "cloud security", "description": ""}
    poor = {"id": "b", "naics": "999999", "agency": "Dept of Fish", "set_aside": None,
            "title": "catering", "description": ""}
    ranked = fit.rank([poor, good], PLAN)
    assert [o["id"] for o in ranked] == ["a", "b"]
    assert ranked[0]["fit_score"] > ranked[1]["fit_score"]


def test_ranking_without_a_plan_preserves_order():
    items = [{"id": "a"}, {"id": "b"}]
    ranked = fit.rank(items, None)
    assert [o["id"] for o in ranked] == ["a", "b"]
    assert all(o["fit_score"] is None for o in ranked)


# --- contact discovery --------------------------------------------------------


def test_published_contact_is_preferred_over_guessing():
    result = email_discovery.discover(
        {
            "id": "X",
            "agency": "Dept Of Defense",
            "office": "USPFO",
            "kind": "solicitation",
            "close_date": "2026-08-14",
            "_point_of_contact": SAM_RECORD["pointOfContact"],
        }
    )
    assert result["email"] == "argenies.e.gonzalezgarcia.mil@army.mil"
    assert result["name"] == "Argenies Gonzalez"
    assert result["title"] == "Contracting Officer"
    assert result["confidence"] >= 0.9


def test_open_solicitation_sets_the_integrity_flag():
    # A close date in the FUTURE — the flag now tracks whether the window is
    # actually open, not merely whether a close date exists (a hardcoded date
    # here started failing the day it passed, which is the fix working).
    still_open = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    result = email_discovery.discover(
        {"id": "X", "agency": "Dept Of Defense", "office": "", "kind": "solicitation",
         "close_date": still_open, "_point_of_contact": SAM_RECORD["pointOfContact"]}
    )
    assert result["active_solicitation"] is True


def test_expiring_award_does_not_set_the_integrity_flag():
    """No open solicitation means outreach isn't constrained the same way."""
    result = email_discovery.discover(
        {"id": "X", "agency": "Dept Of Defense", "office": "", "kind": "expiring_award",
         "close_date": None, "_point_of_contact": SAM_RECORD["pointOfContact"]}
    )
    assert result["active_solicitation"] is False


def test_no_contact_information_returns_none_not_a_guess():
    assert email_discovery.discover(
        {"id": "X", "agency": "", "office": "", "kind": "solicitation", "_point_of_contact": []}
    ) is None


def test_inferred_addresses_are_capped_below_published_ones():
    """A pattern guess must never look as trustworthy as a published address."""
    guesses = email_discovery.candidates("Jane Q Smith", "army.mil")
    assert guesses[0][0] == "jane.smith@army.mil"
    assert all(confidence <= 0.5 for _, confidence in guesses)


def test_name_parsing_strips_the_parenthetical_title():
    assert email_discovery._split_name("Argenies Gonzalez (Contracting Officer)") == (
        "argenies", "", "gonzalez",
    )


@pytest.mark.parametrize(
    "agency,expected",
    [
        ("Dept Of The Army", "army.mil"),
        ("Department of the Navy", "navy.mil"),
        ("Department of Veterans Affairs", "va.gov"),
        ("General Services Administration", "gsa.gov"),
        ("Ministry of Silly Walks", None),
    ],
)
def test_agency_domain_lookup(agency, expected):
    assert email_discovery.domain_for_agency(agency) == expected


# --- bedrock cost guard --------------------------------------------------------


def test_extraction_is_capped_in_bedrock_mode(monkeypatch):
    """One model call per section: a 550-section document must not buy 550
    Bedrock calls off a single detail-view click. Capped with a log line —
    never silently."""
    from app import config
    from app.llm import gateway

    monkeypatch.setattr(config, "LLM_MODE", "bedrock")
    monkeypatch.setattr(config, "LLM_MAX_EXTRACT_SECTIONS", 5)
    calls = {"n": 0}

    def fake_raw(section_text):
        calls["n"] += 1
        return []

    monkeypatch.setattr(gateway, "_raw_obligations_for", fake_raw)
    sections = [{"ref": f"p{i}", "page": i, "text": f"section {i} text"} for i in range(50)]
    gateway.extract_obligations(sections)
    assert calls["n"] == 5, f"expected the cap to hold at 5 calls, got {calls['n']}"


def test_extraction_is_uncapped_in_mock_mode(monkeypatch):
    """The cap is a COST guard; free mock mode reads everything."""
    from app import config
    from app.llm import gateway

    monkeypatch.setattr(config, "LLM_MODE", "mock")
    monkeypatch.setattr(config, "LLM_MAX_EXTRACT_SECTIONS", 5)
    calls = {"n": 0}

    def fake_raw(section_text):
        calls["n"] += 1
        return []

    monkeypatch.setattr(gateway, "_raw_obligations_for", fake_raw)
    sections = [{"ref": f"p{i}", "page": i, "text": f"section {i} text"} for i in range(50)]
    gateway.extract_obligations(sections)
    assert calls["n"] == 50
