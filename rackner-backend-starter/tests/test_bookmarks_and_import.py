"""Bookmarks + PDF import (production-handoff contract) and the audit-2 fixes."""

from __future__ import annotations

import datetime
import io

import pytest

from app.database import SessionLocal
from app.models import Bookmark, Opportunity, SourceDocument, User


@pytest.fixture()
def seeded_opp(client, auth_headers):
    db = SessionLocal()
    try:
        row = db.get(Opportunity, "BM-1") or Opportunity(id="BM-1", title="Bookmarkable", agency="DoD")
        db.add(row)
        db.commit()
    finally:
        db.close()
    return "BM-1"


# --- bookmarks -----------------------------------------------------------------


def test_bookmark_save_list_unsave_roundtrip(client, auth_headers, seeded_opp):
    assert client.put(f"/profile/bookmarks/{seeded_opp}", headers=auth_headers).status_code == 204
    assert client.put(f"/profile/bookmarks/{seeded_opp}", headers=auth_headers).status_code == 204  # idempotent
    assert seeded_opp in client.get("/profile/bookmarks", headers=auth_headers).json()
    assert client.delete(f"/profile/bookmarks/{seeded_opp}", headers=auth_headers).status_code == 204
    assert client.delete(f"/profile/bookmarks/{seeded_opp}", headers=auth_headers).status_code == 204  # idempotent
    assert seeded_opp not in client.get("/profile/bookmarks", headers=auth_headers).json()


def test_bookmarking_an_unknown_opportunity_is_404(client, auth_headers):
    assert client.put("/profile/bookmarks/NOPE-404", headers=auth_headers).status_code == 404


# --- import --------------------------------------------------------------------

PLAN_TEXT = (
    b"SECTION C - STATEMENT OF WORK\n"
    b"The Contractor shall provide cybersecurity engineering services.\n"
    b"C.2 Reporting\n"
    b"The Contractor shall deliver a monthly status report.\n"
)


def _import(client, auth_headers, content=PLAN_TEXT, name="uploaded-solicitation.txt"):
    return client.post(
        "/opportunities/import",
        headers=auth_headers,
        files={"file": (name, io.BytesIO(content), "text/plain")},
    )


def test_import_runs_the_full_pipeline(client, auth_headers):
    r = _import(client, auth_headers)
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["id"].startswith("imp_"), "import ids must be unmistakable"
    assert summary["title"], "a title always exists (filename fallback)"

    # The grounding document was built at import time from the FULL text.
    doc = client.get(f"/opportunities/{summary['id']}/document", headers=auth_headers).json()
    text = "\n".join(s["text"] for s in doc["sections"])
    assert "monthly status report" in text

    # Analysis and chat work like any other opportunity.
    a = client.get(f"/opportunities/{summary['id']}/analysis", headers=auth_headers).json()
    assert a["band"] in ("pursue", "conditional", "no_bid")
    c = client.post(
        f"/opportunities/{summary['id']}/chat",
        headers=auth_headers,
        json={"question": "What must be delivered monthly?"},
    ).json()
    assert c["answer"]


def test_reimporting_identical_bytes_dedupes(client, auth_headers):
    first = _import(client, auth_headers, name="dupe.txt").json()
    second = _import(client, auth_headers, name="dupe-renamed.txt").json()
    assert first["id"] == second["id"], "same bytes, same uploader -> same record"


def test_imported_documents_are_private(client, auth_headers, seeded_opp):
    imported = _import(client, auth_headers, content=PLAN_TEXT + b"private variant\n").json()

    other = {"email": "import-other@rackner.com", "password": "import-other-pw-1"}
    client.post("/auth/register", json=other)
    r = client.post("/auth/login", json=other)
    other_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert (
        client.get(f"/opportunities/{imported['id']}", headers=other_headers).status_code
        == 404
    ), "a stranger must not even learn the import exists"
    assert (
        client.get(f"/opportunities/{imported['id']}/document", headers=other_headers).status_code
        == 404
    )
    assert (
        client.put(f"/profile/bookmarks/{imported['id']}", headers=other_headers).status_code
        == 404
    )
    # ...and it never shows in shared cached lists
    from app.routes.opportunities import _cached_sam_rows

    db = SessionLocal()
    try:
        rows = _cached_sam_rows(db, query="", kinds=[], limit=200)
    finally:
        db.close()
    assert all(not r["id"].startswith("imp_") for r in rows)


def test_import_rejects_empty_and_unreadable(client, auth_headers):
    assert _import(client, auth_headers, content=b"").status_code == 400


# --- audit-2 breaking fixes ------------------------------------------------------


def test_fresh_search_row_still_gets_its_description_fetched(client, auth_headers, monkeypatch):
    """The audit-2 regression: the empty-description guard keyed off
    fetched_at (bumped by search), so a freshly searched row NEVER got its
    description on first click. It must fetch exactly once, then stop."""
    from app.services import samgov

    calls = {"n": 0}

    def fake_get(notice_id, **kw):
        calls["n"] += 1
        return {
            "id": notice_id, "title": "Fresh row", "agency": "DoD", "office": None,
            "solicitation_number": None, "naics": None, "set_aside": None,
            "kind": "solicitation", "description": "", "close_date": None,
            "days_to_close": None, "est_value": None, "incumbent": None,
            "fit_score": None, "expiry_date": None, "months_to_expiry": None,
            "current_award_value": None, "_description_url": "https://x/desc",
        }

    monkeypatch.setattr(samgov, "get_opportunity", fake_get)
    monkeypatch.setattr(samgov, "fetch_description", lambda url: "")  # genuinely empty
    monkeypatch.setattr(samgov, "is_configured", lambda: True)

    db = SessionLocal()
    try:
        row = db.get(Opportunity, "FRESHDESC-1") or Opportunity(
            id="FRESHDESC-1", title="Fresh row", agency="DoD"
        )
        row.description = ""
        row.description_fetched_at = None
        db.add(row)
        db.commit()  # fetched_at = NOW, as a search would leave it
    finally:
        db.close()

    client.get("/opportunities/FRESHDESC-1", headers=auth_headers)
    assert calls["n"] == 1, "the FIRST detail view must fetch the description"
    client.get("/opportunities/FRESHDESC-1", headers=auth_headers)
    assert calls["n"] == 1, "a recorded attempt must not be repeated inside the TTL"


def test_query_filtered_search_does_not_poison_the_radar(client, auth_headers, monkeypatch):
    """audit-2: a q-filtered search cached only matching awards while
    stamping the window fresh — the dashboard lost the rest for 12h. The
    full fetched set must be cached BEFORE filtering."""
    from app.services import usaspending

    expiry = (datetime.date.today() + datetime.timedelta(days=450)).isoformat()

    def awards(**kw):
        base = {
            "office": None, "solicitation_number": None, "naics": None,
            "set_aside": None, "kind": "expiring_award", "description": "",
            "close_date": None, "days_to_close": None, "est_value": None,
            "fit_score": None, "expiry_date": expiry, "months_to_expiry": 15,
            "current_award_value": 5.0,
        }
        return [
            {**base, "id": "AWD-CYBER", "title": "Cyber ops award", "agency": "DoD", "incumbent": None},
            {**base, "id": "AWD-CATERING", "title": "Catering services award", "agency": "USDA", "incumbent": None},
        ]

    monkeypatch.setattr(usaspending, "expiring_awards", awards)

    # A q-filtered search: only the cyber award survives the response...
    r = client.get("/opportunities/search?q=cyber&kinds=expiring_award", headers=auth_headers)
    ids = {row["id"] for row in r.json()}
    assert "AWD-CYBER" in ids and "AWD-CATERING" not in ids

    # ...but the replayed dashboard (same fresh window) must have BOTH.
    r = client.get("/opportunities/search?q=&kinds=expiring_award", headers=auth_headers)
    ids = {row["id"] for row in r.json()}
    assert {"AWD-CYBER", "AWD-CATERING"} <= ids, "the full fetched set must be cached"


def test_replay_does_not_bump_fetched_at(client, auth_headers, monkeypatch):
    from app.services import samgov

    monkeypatch.setattr(
        samgov, "search",
        lambda query, kinds=None, limit=25, **kw: [{
            "id": "REPLAY-1", "title": "Replay bump check", "agency": "DoD", "office": None,
            "solicitation_number": None, "naics": None, "set_aside": None,
            "kind": "solicitation", "description": "", "close_date": None,
            "days_to_close": None, "est_value": None, "incumbent": None,
            "fit_score": None, "expiry_date": None, "months_to_expiry": None,
            "current_award_value": None,
        }],
    )
    monkeypatch.setattr(samgov, "is_configured", lambda: True)

    client.get("/opportunities/search?q=replay+bump+check", headers=auth_headers)
    db = SessionLocal()
    try:
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=6)
        db.execute(
            Opportunity.__table__.update()
            .where(Opportunity.id == "REPLAY-1")
            .values(fetched_at=old)
        )
        db.commit()
    finally:
        db.close()

    # Replay (fresh ledger) — must NOT re-stamp the row as fresh.
    client.get("/opportunities/search?q=replay+bump+check", headers=auth_headers)
    db = SessionLocal()
    try:
        fetched = db.get(Opportunity, "REPLAY-1").fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=datetime.timezone.utc)
        age_h = (datetime.datetime.now(datetime.timezone.utc) - fetched).total_seconds() / 3600
    finally:
        db.close()
    assert age_h > 5, "a zero-cost replay must not corrupt freshness"
