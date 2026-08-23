"""Third-party email verification (services/email_verify) — feature-flagged.

The contract under test, in order of importance:
  * provider "none" (the suite default): ZERO outbound calls, discovery
    byte-identical to the pre-feature build.
  * Fail-soft everywhere: timeout, non-200, daily cap → "unverified" and
    discovery proceeds exactly as today. Never a 500.
  * Tier 1 (SAM-published) never triggers a verification call.
  * invalid top candidate falls through to the next; all-invalid → no contact.
  * valid rises to confidence ≤ 0.75 — always below Tier 1's 0.85/0.95.
  * The TTL keeps cached contacts from re-verifying on every read.

No live provider calls anywhere here — requests is monkeypatched at the
email_verify module boundary.
"""

from __future__ import annotations

import datetime

import pytest

from app import config
from app.database import SessionLocal
from app.models import Contact, Opportunity
from app.services import email_discovery, email_verify

TIER2_OPP = {
    "id": "VER-1",
    "agency": "Dept of Defense",
    "office": "",
    "kind": "solicitation",
    "close_date": None,
    "_point_of_contact": [{"fullName": "Jane Doe", "email": ""}],
}

TIER1_OPP = {
    "id": "VER-2",
    "agency": "Dept of Defense",
    "office": "",
    "kind": "solicitation",
    "close_date": None,
    "_point_of_contact": [
        {"fullName": "Jane Doe", "email": "jane.doe@mail.mil", "type": "primary"}
    ],
}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _generect_response(result: str):
    return _Resp({"data": [{"result": result}], "meta": {"amount_charged": 0.005}})


@pytest.fixture
def generect(monkeypatch):
    """Switch the provider on and capture outbound calls; each test sets the
    scripted results it wants (a list popped per call)."""
    monkeypatch.setattr(config, "EMAIL_VERIFY_PROVIDER", "generect")
    monkeypatch.setattr(config, "GENERECT_API_KEY", "test-key")
    calls = {"n": 0, "script": []}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        step = calls["script"].pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    monkeypatch.setattr(email_verify.requests, "post", fake_post)
    return calls


def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("outbound verification call with provider off")

    monkeypatch.setattr(email_verify.requests, "post", boom)
    monkeypatch.setattr(email_verify.requests, "get", boom)


def test_provider_none_makes_no_calls_and_is_identical(monkeypatch):
    _no_network(monkeypatch)
    result = email_discovery.discover(TIER2_OPP)
    assert result["email"] == "jane.doe@mail.mil"
    assert result["confidence"] == 0.45
    assert result["verification"] is None


def test_tier1_never_verifies_even_with_provider_on(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_VERIFY_PROVIDER", "generect")
    _no_network(monkeypatch)  # any call raises
    result = email_discovery.discover(TIER1_OPP)
    assert result["email"] == "jane.doe@mail.mil"
    assert result["confidence"] == 0.95


def test_valid_candidate_rises_but_caps_below_tier1(generect):
    generect["script"] = [_generect_response("valid")]
    result = email_discovery.discover(TIER2_OPP)
    assert result["email"] == "jane.doe@mail.mil"
    assert result["confidence"] == 0.75
    assert result["confidence"] < 0.85  # the tier boundary, stated
    assert result["verification"]["status"] == "valid"
    assert result["verification"]["provider"] == "generect"


def test_invalid_falls_through_to_next_candidate(generect):
    generect["script"] = [_generect_response("invalid"), _generect_response("valid")]
    result = email_discovery.discover(TIER2_OPP)
    # first pattern (jane.doe@) dropped; second (jane.<middle>.doe has no
    # middle, so jdoe@) served
    assert result["email"] == "jdoe@mail.mil"
    assert result["verification"]["status"] == "valid"
    assert generect["n"] == 2


def test_fallthrough_survivor_keeps_its_own_prior(generect):
    # Audit finding: the survivor must NOT inherit the dropped front-runner's
    # confidence — jdoe@'s own pattern prior is 0.15, not jane.doe@'s 0.45.
    generect["script"] = [_generect_response("invalid"), _generect_response("catch_all")]
    result = email_discovery.discover(TIER2_OPP)
    assert result["email"] == "jdoe@mail.mil"
    assert result["confidence"] == 0.15
    assert result["verification"]["status"] == "accept_all"


def test_all_top_candidates_invalid_means_no_contact(generect):
    generect["script"] = [_generect_response("invalid")] * 3
    result = email_discovery.discover(TIER2_OPP)
    assert result == {"none_valid": True}
    assert generect["n"] == 3


def test_catch_all_keeps_todays_cap(generect):
    generect["script"] = [_generect_response("catch_all")]
    result = email_discovery.discover(TIER2_OPP)
    assert result["email"] == "jane.doe@mail.mil"
    assert result["confidence"] == 0.45  # unchanged
    assert result["verification"]["status"] == "accept_all"


def test_timeout_degrades_to_unverified(generect):
    generect["script"] = [TimeoutError("slow provider")]
    result = email_discovery.discover(TIER2_OPP)
    assert result["email"] == "jane.doe@mail.mil"
    assert result["confidence"] == 0.45
    assert result["verification"] is None  # no answer -> nothing recorded


def test_daily_cap_stops_outbound_calls(generect, monkeypatch):
    monkeypatch.setattr(config, "EMAIL_VERIFY_DAILY_CAP", 2)
    generect["script"] = [_generect_response("valid")] * 2
    assert email_verify.verify("a@x.mil")["status"] == "valid"
    assert email_verify.verify("b@x.mil")["status"] == "valid"
    # Third call: cap reached — no outbound request is even attempted.
    assert email_verify.verify("c@x.mil")["status"] == "unverified"
    assert generect["n"] == 2


def _seed_contact(opp_id: str, checked_at):
    db = SessionLocal()
    try:
        if db.get(Opportunity, opp_id) is None:
            db.add(Opportunity(id=opp_id, title="t", agency="a"))
        db.query(Contact).filter_by(opportunity_id=opp_id).delete()
        db.add(
            Contact(
                opportunity_id=opp_id,
                name="Jane Doe",
                title="CO",
                office="o",
                email="jane.doe@mail.mil",
                confidence=0.45,
                verification_status="valid" if checked_at else None,
                verification_provider="generect" if checked_at else None,
                verification_checked_at=checked_at,
            )
        )
        db.commit()
    finally:
        db.close()


def test_ttl_prevents_reverify_inside_window(client, auth_headers, generect):
    now = datetime.datetime.now(datetime.timezone.utc)
    _seed_contact("TTL-FRESH-1", now - datetime.timedelta(days=1))
    r = client.get("/opportunities/TTL-FRESH-1/contact", headers=auth_headers)
    assert r.status_code == 200
    assert generect["n"] == 0, "fresh verification must not re-check"
    assert r.json()["verification"]["status"] == "valid"


def test_expired_ttl_reverifies_once(client, auth_headers, generect):
    now = datetime.datetime.now(datetime.timezone.utc)
    _seed_contact("TTL-OLD-1", now - datetime.timedelta(days=45))
    generect["script"] = [_generect_response("catch_all")]
    r = client.get("/opportunities/TTL-OLD-1/contact", headers=auth_headers)
    assert r.status_code == 200
    assert generect["n"] == 1
    assert r.json()["verification"]["status"] == "accept_all"
    # And the refreshed stamp means the NEXT read is quiet again.
    r = client.get("/opportunities/TTL-OLD-1/contact", headers=auth_headers)
    assert generect["n"] == 1


def test_verification_failure_never_500s_the_route(client, auth_headers, generect):
    now = datetime.datetime.now(datetime.timezone.utc)
    _seed_contact("TTL-ERR-1", now - datetime.timedelta(days=45))
    generect["script"] = [RuntimeError("provider exploded")]
    r = client.get("/opportunities/TTL-ERR-1/contact", headers=auth_headers)
    assert r.status_code == 200  # fail-soft: stale-but-served beats erroring


def test_flag_off_serves_null_verification_even_for_verified_rows(
    client, auth_headers, monkeypatch
):
    """SCHEMA_v2: verification is ALWAYS null while the feature is off —
    including rows verified during an earlier flag-on trial (their stored
    status only grows staler once re-verification is disabled)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    _seed_contact("FLAG-OFF-1", now - datetime.timedelta(days=1))
    monkeypatch.setattr(config, "EMAIL_VERIFY_PROVIDER", "none")
    _no_network(monkeypatch)
    r = client.get("/opportunities/FLAG-OFF-1/contact", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["verification"] is None


def _seed_opp_only(opp_id: str):
    db = SessionLocal()
    try:
        if db.get(Opportunity, opp_id) is None:
            db.add(Opportunity(id=opp_id, title="t", agency="Dept of Defense"))
        db.query(Contact).filter_by(opportunity_id=opp_id).delete()
        db.commit()
    finally:
        db.close()


def test_all_invalid_is_cached_not_respent(client, auth_headers, generect, monkeypatch):
    """Audit finding: the all-invalid verdict must be cached. Un-cached, every
    read re-spent 3 provider credits, and a tripped daily cap then served the
    very address the provider had just proven nonexistent."""
    _seed_opp_only("ALLINV-1")
    # Give discovery an email-less POC via the route's SAM refetch, so Tier 2
    # (and the verifier) is what runs.
    from app.routes import contacts as contacts_route

    monkeypatch.setattr(contacts_route.samgov, "is_configured", lambda: True)
    monkeypatch.setattr(
        contacts_route.samgov,
        "get_opportunity",
        lambda _id: {"_point_of_contact": [{"fullName": "Jane Doe", "email": ""}]},
    )
    generect["script"] = [_generect_response("invalid")] * 3

    r = client.get("/opportunities/ALLINV-1/contact", headers=auth_headers)
    assert r.status_code == 404
    assert generect["n"] == 3

    # Second read: served from the negative cache — zero further spend.
    r = client.get("/opportunities/ALLINV-1/contact", headers=auth_headers)
    assert r.status_code == 404
    assert generect["n"] == 3

    # Once the verdict ages past the TTL, discovery runs again.
    db = SessionLocal()
    try:
        row = db.query(Contact).filter_by(opportunity_id="ALLINV-1").one()
        assert row.email == "" and row.verification_status == "invalid"
        row.verification_checked_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(days=45)
        db.commit()
    finally:
        db.close()
    generect["script"] = [_generect_response("valid")]
    r = client.get("/opportunities/ALLINV-1/contact", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["verification"]["status"] == "valid"
    assert generect["n"] == 4
