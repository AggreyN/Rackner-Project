"""Regression tests for the 2026-08-19 offline audit's confirmed findings."""

from __future__ import annotations

import datetime

import pytest

from app import config
from app.database import SessionLocal
from app.models import Analysis, Opportunity
from app.services import attachments
from app.services.http import UpstreamError, redact


# --- security: key redaction -----------------------------------------------------


def test_api_key_is_redacted_from_error_details():
    msg = "Connection aborted: https://api.sam.gov/x?api_key=SAM-secret123&limit=5"
    assert "SAM-secret123" not in redact(msg)
    assert "api_key=[redacted]" in redact(msg)


# --- attachments: transient vs permanent ------------------------------------------


def _fetch_with(monkeypatch, exc_detail: str):
    from app.services import http

    def dying(url, **kw):
        raise UpstreamError("SAM.gov", exc_detail)

    monkeypatch.setattr(http, "get_bytes", dying)
    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "k")
    return attachments.fetch_all(["https://x/1"])


def test_transient_failure_is_not_resolved(monkeypatch):
    for detail in ("HTTP 503", "timeout after (5, 60)s", "Connection aborted"):
        blobs, exhausted = _fetch_with(monkeypatch, detail)
        assert blobs == [] and exhausted is False, (
            f"{detail!r} must stay retryable — resolving it froze documents partial forever"
        )


def test_permanent_failure_is_resolved(monkeypatch):
    for detail in ("HTTP 404", "HTTP 403", "file exceeds the 25 MB cap"):
        blobs, exhausted = _fetch_with(monkeypatch, detail)
        assert blobs == [] and exhausted is True, f"{detail!r} should never be retried"


# --- cache: fetched_at bumps on update --------------------------------------------


def test_cache_update_refreshes_fetched_at(client, auth_headers):
    from app.routes.opportunities import _cache

    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)
    db = SessionLocal()
    try:
        row = db.get(Opportunity, "AUDIT-F2") or Opportunity(
            id="AUDIT-F2", title="stale", agency="DoD"
        )
        db.add(row)
        db.commit()
        db.execute(
            Opportunity.__table__.update()
            .where(Opportunity.id == "AUDIT-F2")
            .values(fetched_at=old)
        )
        db.commit()

        _cache(db, [{"id": "AUDIT-F2", "title": "fresh again", "agency": "DoD"}])
        db.expire_all()
        fetched = db.get(Opportunity, "AUDIT-F2").fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=datetime.timezone.utc)
        age = datetime.datetime.now(datetime.timezone.utc) - fetched
        assert age.total_seconds() < 60, "a live re-fetch must make the row fresh NOW"
    finally:
        db.close()


# --- analysis score clamp ----------------------------------------------------------


def test_out_of_range_persisted_score_still_serves(client, auth_headers):
    from app.routes.analysis import _to_schema

    db = SessionLocal()
    try:
        row = Analysis(
            opportunity_id="AUDIT-F2", user_id=1, score=142.5, band="pursue",
            verdict="wild", factors=[], obligations=[],
        )
        out = _to_schema(row)
        assert out.score == 100.0, "legacy out-of-range rows must clamp, not 500"
    finally:
        db.close()


def test_analyze_clamps_score_at_write(monkeypatch):
    from app.llm import gateway

    monkeypatch.setattr(gateway, "_score", lambda factors: 240.0)
    monkeypatch.setattr(config, "LLM_MODE", "mock")
    result = gateway.analyze({"id": "X"}, {}, [])
    assert result["score"] == 100.0


# --- plan upload invalidates analyses ----------------------------------------------


def test_new_plan_deletes_the_users_analyses(client, auth_headers):
    import io

    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="pytest@rackner.com").one()
        opp = db.get(Opportunity, "AUDIT-PLAN") or Opportunity(
            id="AUDIT-PLAN", title="t", agency="DoD"
        )
        db.add(opp)
        db.query(Analysis).filter_by(opportunity_id="AUDIT-PLAN").delete()
        db.commit()
        db.add(
            Analysis(
                opportunity_id="AUDIT-PLAN", user_id=user.id, score=10.0,
                band="no_bid", verdict="old profile", factors=[], obligations=[],
            )
        )
        db.commit()
        uid = user.id
    finally:
        db.close()

    r = client.post(
        "/profile/lifecycle",
        headers=auth_headers,
        files={"file": ("plan.txt", io.BytesIO(b"Capabilities: cyber\nNAICS: 541512\n"), "text/plain")},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        left = db.query(Analysis).filter_by(user_id=uid).count()
    finally:
        db.close()
    assert left == 0, "old-profile analyses must not outlive the plan that shaped them"


# --- text-less attachments don't trigger destructive rebuilds ----------------------


def test_textless_attachment_does_not_rebuild_or_invalidate(client, auth_headers, monkeypatch):
    from app.models import SourceDocument, User

    opp_id = "AUDIT-TEXTLESS"
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="pytest@rackner.com").one()
        row = db.get(Opportunity, opp_id) or Opportunity(id=opp_id, title="t", agency="DoD")
        db.add(row)
        row.description = "The Contractor shall do things."
        row.resource_links = ["https://x/1"]
        for d in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(d)
        db.query(Analysis).filter_by(opportunity_id=opp_id).delete()
        db.commit()
        uid = user.id
    finally:
        db.close()

    # First build: no attachments fetchable yet (quota) -> description-only doc.
    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([], False))
    client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)

    db = SessionLocal()
    try:
        doc_id = db.query(SourceDocument).filter_by(opportunity_id=opp_id).one().id
        db.add(Analysis(opportunity_id=opp_id, user_id=uid, score=50.0,
                        band="conditional", verdict="v", factors=[], obligations=[]))
        db.commit()
    finally:
        db.close()

    # Attachment now fetches but yields NO text (an image-only PDF with OCR
    # off — load_text legitimately returns "").
    from app.services import ingest

    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([b"%PDF-imageonly"], True))
    monkeypatch.setattr(ingest, "load_text", lambda blob, filename="": "")
    r = client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    assert r.status_code == 200

    db = SessionLocal()
    try:
        doc_id_after = db.query(SourceDocument).filter_by(opportunity_id=opp_id).one().id
        analyses = db.query(Analysis).filter_by(opportunity_id=opp_id).count()
    finally:
        db.close()
    assert doc_id_after == doc_id, "identical grounding text must not rebuild"
    assert analyses == 1, "no rebuild -> no analysis invalidation"


# --- empty-description detail views stop refetching --------------------------------


def test_recently_fetched_empty_description_row_skips_sam(client, auth_headers, monkeypatch):
    from app.services import samgov

    calls = {"n": 0}

    def counting_get(notice_id, **kw):
        calls["n"] += 1
        return None

    monkeypatch.setattr(samgov, "get_opportunity", counting_get)
    monkeypatch.setattr(samgov, "is_configured", lambda: True)

    db = SessionLocal()
    try:
        row = db.get(Opportunity, "AUDIT-EMPTYDESC") or Opportunity(
            id="AUDIT-EMPTYDESC", title="No description notice", agency="DoD"
        )
        row.description = ""
        # The corrected guard keys off an actual DETAIL attempt, not search
        # freshness (audit-2: keying off fetched_at blocked first fetches).
        row.description_fetched_at = datetime.datetime.now(datetime.timezone.utc)
        db.add(row)
        db.commit()
    finally:
        db.close()

    for _ in range(3):
        r = client.get("/opportunities/AUDIT-EMPTYDESC", headers=auth_headers)
        assert r.status_code == 200
    assert calls["n"] == 0, "a recorded description attempt must not be repeated in the TTL"


def test_delete_lifecycle_plan_removes_plan_and_scores(client, auth_headers):
    import io

    from app.models import FitEstimate, User

    r = client.post(
        "/profile/lifecycle",
        headers=auth_headers,
        files={"file": ("plan.txt", io.BytesIO(b"Capabilities: cyber\nNAICS: 541512\n"), "text/plain")},
    )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="pytest@rackner.com").one()
        opp = db.get(Opportunity, "AUDIT-DEL") or Opportunity(id="AUDIT-DEL", title="t", agency="DoD")
        db.add(opp)
        db.commit()  # FK target must exist before the estimate row (Postgres enforces)
        db.add(FitEstimate(user_id=user.id, opportunity_id="AUDIT-DEL", score=50.0))
        db.commit()
        uid = user.id
    finally:
        db.close()

    r = client.delete("/profile/lifecycle", headers=auth_headers)
    assert r.status_code == 204

    prof = client.get("/profile", headers=auth_headers).json()
    assert prof["lifecycle"] is None, "the plan must be gone"

    db = SessionLocal()
    try:
        assert db.query(FitEstimate).filter_by(user_id=uid).count() == 0
        assert db.query(Analysis).filter_by(user_id=uid).count() == 0
    finally:
        db.close()

    r = client.delete("/profile/lifecycle", headers=auth_headers)
    assert r.status_code == 404, "deleting a non-existent plan is a clean 404"


# --- usernames: Cognito name claim -> display_name -> profile ----------------------


def test_cognito_name_claim_syncs_to_profile(client, auth_headers, monkeypatch):
    from app import auth as auth_module
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email="pytest@rackner.com").one()
        claims = {"sub": "test-sub-username", "email": user.email, "name": "Py Test"}
        auth_module._upsert_cognito_user(claims, db)
        db.refresh(user)
        assert user.display_name == "Py Test"

        # Renaming in the pool updates on the next request; same name is a no-op.
        auth_module._upsert_cognito_user({**claims, "name": "Py T. Renamed"}, db)
        db.refresh(user)
        assert user.display_name == "Py T. Renamed"
    finally:
        user.display_name = "Py Test"  # leave deterministic state
        db.commit()
        db.close()

    prof = client.get("/profile", headers=auth_headers).json()
    assert prof["user"]["username"] == "Py Test"
    assert prof["user"]["initials"] == "PT", "initials come from the display name"
