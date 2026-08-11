"""Full-document ingestion: SAM attachments become grounding text.

The invariants under test:
  * the document is description + every fetchable attachment, built once;
  * a stored document only ever GROWS, and any growth deletes the
    opportunity's stored analyses (their citations were verified against the
    old text — grounding text must never change underneath a citation);
  * a fetch that yields nothing new (dead quota, broken links) leaves the
    stored document and its analyses untouched — no thrash;
  * downloads stop instantly on a 429 (daily quota is spent; further calls
    are pure waste) and skip formats the pipeline can't honestly ingest.
"""

from __future__ import annotations

import pytest

from app import config
from app.database import SessionLocal
from app.models import Analysis, Opportunity, SourceDocument, User
from app.services import attachments
from app.services.http import UpstreamError

ATTACHMENT_TEXT = (
    "SECTION C - STATEMENT OF WORK\n"
    "The Contractor shall provide widget maintenance services.\n"
    "C.2 Deliverables\n"
    "The Contractor shall deliver a monthly status report."
)


@pytest.fixture()
def opp_with_links(client, auth_headers):
    opp_id = "FULLDOC-1"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id)
        if row is None:
            row = Opportunity(id=opp_id, title="Full doc target", agency="DoD")
            db.add(row)
        row.description = "Summary: widget maintenance services solicitation."
        row.resource_links = ["https://api.sam.gov/x/files/1/download"]
        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.query(Analysis).filter_by(opportunity_id=opp_id).delete()
        db.commit()
    finally:
        db.close()
    return opp_id


def _doc_row(opp_id):
    db = SessionLocal()
    try:
        doc = (
            db.query(SourceDocument).filter_by(opportunity_id=opp_id).one_or_none()
        )
        if doc is None:
            return None, "", 0
        text = "\n".join(s.text for s in doc.sections)
        return doc.id, text, doc.attachments_ingested
    finally:
        db.close()


def _add_analysis(opp_id) -> int:
    db = SessionLocal()
    try:
        user = db.query(User).first()
        row = Analysis(
            opportunity_id=opp_id,
            user_id=user.id,
            score=50.0,
            band="conditional",
            verdict="stale",
            factors=[],
            obligations=[],
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _analysis_count(opp_id) -> int:
    db = SessionLocal()
    try:
        return db.query(Analysis).filter_by(opportunity_id=opp_id).count()
    finally:
        db.close()


# --- build + build-once --------------------------------------------------------


def test_first_build_includes_attachment_text(client, auth_headers, opp_with_links, monkeypatch):
    monkeypatch.setattr(
        attachments, "fetch_all", lambda links: ([ATTACHMENT_TEXT.encode()], True)
    )
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert r.status_code == 200, r.text
    text = "\n".join(s["text"] for s in r.json()["sections"])
    assert "widget maintenance services solicitation" in text, "description kept"
    assert "monthly status report" in text, "attachment text ingested"
    _, _, ingested = _doc_row(opp_with_links)
    assert ingested == 1


def test_attachments_are_fetched_exactly_once(client, auth_headers, opp_with_links, monkeypatch):
    calls = {"n": 0}

    def counting_fetch(links):
        calls["n"] += 1
        return ([ATTACHMENT_TEXT.encode()], True)

    monkeypatch.setattr(attachments, "fetch_all", counting_fetch)
    for _ in range(3):
        assert (
            client.get(
                f"/opportunities/{opp_with_links}/document", headers=auth_headers
            ).status_code
            == 200
        )
    assert calls["n"] == 1, "build-once: later reads must not re-download"


# --- growth + invalidation -----------------------------------------------------


def test_document_grows_and_stale_analyses_die(client, auth_headers, opp_with_links, monkeypatch):
    # First build: quota dead, no attachments land.
    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([], False))
    client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    doc_id_before, text_before, ingested = _doc_row(opp_with_links)
    assert ingested == 0 and "monthly status report" not in text_before

    _add_analysis(opp_with_links)

    # Quota back: the attachment now fetches -> document grows, analyses reset.
    monkeypatch.setattr(
        attachments, "fetch_all", lambda links: ([ATTACHMENT_TEXT.encode()], True)
    )
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    text_after = "\n".join(s["text"] for s in r.json()["sections"])
    assert "monthly status report" in text_after
    _, _, ingested_after = _doc_row(opp_with_links)
    assert ingested_after == 1
    assert _analysis_count(opp_with_links) == 0, (
        "analyses verified against the smaller document must not survive growth"
    )


def test_failed_refetch_keeps_document_and_analyses(client, auth_headers, opp_with_links, monkeypatch):
    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([], False))
    client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    doc_id, _, _ = _doc_row(opp_with_links)
    _add_analysis(opp_with_links)

    # Still nothing fetchable — the stored build must survive untouched.
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert r.status_code == 200
    doc_id_after, _, _ = _doc_row(opp_with_links)
    assert doc_id_after == doc_id, "no-op fetch must not rebuild"
    assert _analysis_count(opp_with_links) == 1, "no-op fetch must not invalidate"


def test_partial_then_full_fetch_upgrades(client, auth_headers, opp_with_links, monkeypatch):
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_with_links)
        row.resource_links = ["https://x/1", "https://x/2"]
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([b"PART ONE ONLY"], False))
    client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert _doc_row(opp_with_links)[2] == 1

    monkeypatch.setattr(
        attachments, "fetch_all", lambda links: ([b"PART ONE ONLY", b"PART TWO NOW"], True)
    )
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert "PART TWO NOW" in "\n".join(s["text"] for s in r.json()["sections"])
    assert _doc_row(opp_with_links)[2] == 2


def test_dead_links_are_resolved_once_not_retried_forever(
    client, auth_headers, opp_with_links, monkeypatch
):
    """A permanently-404 or unsupported-format link must not cost a download
    attempt on every read (chat rebuilds the doc per message). One exhausted
    pass resolves it for good."""
    calls = {"n": 0}

    def all_links_dead(links):
        calls["n"] += 1
        return ([], True)  # exhausted: nothing fetchable, retrying won't help

    monkeypatch.setattr(attachments, "fetch_all", all_links_dead)
    for _ in range(4):
        r = client.get(
            f"/opportunities/{opp_with_links}/document", headers=auth_headers
        )
        assert r.status_code == 200
    assert calls["n"] == 1, "resolved-dead links must never be re-attempted"


def test_late_description_gets_into_the_document(client, auth_headers, monkeypatch):
    """Search persists links before the detail path fetches the description —
    a document built attachments-first must still gain the description later,
    and the rebuild must invalidate analyses like any other change."""
    opp_id = "FULLDOC-LATE-DESC"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id) or Opportunity(
            id=opp_id, title="Late description", agency="DoD"
        )
        db.add(row)
        row.description = ""  # not fetched yet
        row.resource_links = ["https://x/1"]
        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.query(Analysis).filter_by(opportunity_id=opp_id).delete()
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        attachments, "fetch_all", lambda links: ([b"ATTACHMENT BODY TEXT"], True)
    )
    r = client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    assert "ATTACHMENT BODY TEXT" in "\n".join(
        s["text"] for s in r.json()["sections"]
    )
    _add_analysis(opp_id)

    db = SessionLocal()
    try:
        db.get(Opportunity, opp_id).description = "The description arrived late."
        db.commit()
    finally:
        db.close()

    r = client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    text = "\n".join(s["text"] for s in r.json()["sections"])
    assert "description arrived late" in text
    assert "ATTACHMENT BODY TEXT" in text
    assert _analysis_count(opp_id) == 0, "refs shifted; stale analyses must die"


def test_one_document_per_opportunity_is_db_enforced(opp_with_links):
    from sqlalchemy.exc import IntegrityError

    db = SessionLocal()
    try:
        db.add(SourceDocument(opportunity_id=opp_with_links, label="a"))
        db.commit()
        db.add(SourceDocument(opportunity_id=opp_with_links, label="b"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.query(SourceDocument).filter_by(opportunity_id=opp_with_links).delete()
        db.commit()
        db.close()


def test_analysis_is_not_persisted_when_document_rebuilds_mid_generation(
    client, auth_headers, opp_with_links, monkeypatch
):
    """The grounding race: a rebuild landing while the model call is in
    flight must make the analysis transient, never a stored row whose
    citations point at replaced text."""
    from app.llm import gateway

    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([b"V1 TEXT"], True))
    client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)

    real_analyze = gateway.analyze

    def analyze_and_swap_doc(opp_dict, profile, sections):
        result = real_analyze(opp_dict, profile, sections)
        db = SessionLocal()
        try:  # simulate a concurrent rebuild committing mid-generation
            db.query(SourceDocument).filter_by(
                opportunity_id=opp_with_links
            ).delete()
            db.add(
                SourceDocument(
                    opportunity_id=opp_with_links, label="v2", has_description=True
                )
            )
            db.commit()
        finally:
            db.close()
        return result

    monkeypatch.setattr(gateway, "analyze", analyze_and_swap_doc)
    r = client.get(f"/opportunities/{opp_with_links}/analysis", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert _analysis_count(opp_with_links) == 0, (
        "an analysis generated against a replaced document must stay transient"
    )


def test_empty_doc_with_dead_links_stops_fetching_too(client, auth_headers, monkeypatch):
    """The zero-section corner: a description-less opportunity whose links go
    permanently dead must record the exhausted pass on its EMPTY document —
    otherwise every read (and every chat message) refetches forever."""
    opp_id = "FULLDOC-EMPTY-DEAD"
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id) or Opportunity(
            id=opp_id, title="Empty + dead links", agency="DoD"
        )
        db.add(row)
        row.description = ""
        row.resource_links = ["https://x/dead-1", "https://x/dead-2"]
        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.commit()
    finally:
        db.close()

    # First read: quota-stopped -> empty doc, nothing accounted (retry later).
    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([], False))
    client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)

    # Quota back but the links are permanently dead: ONE exhausted pass...
    calls = {"n": 0}

    def dead_links(links):
        calls["n"] += 1
        return ([], True)

    monkeypatch.setattr(attachments, "fetch_all", dead_links)
    for _ in range(3):
        assert (
            client.get(
                f"/opportunities/{opp_id}/document", headers=auth_headers
            ).status_code
            == 200
        )
    assert calls["n"] == 1, "an exhausted pass must be recorded on empty docs too"


def test_losing_a_concurrent_build_race_serves_the_winner_not_a_500(
    client, auth_headers, opp_with_links, monkeypatch
):
    """The unique index makes concurrent builders race; the loser's INSERT
    raises at flush and must degrade to serving the winner's document."""

    def fetch_and_lose_race(links):
        db = SessionLocal()
        try:  # a competing builder (e.g. the prewarm) commits while we fetch
            db.add(
                SourceDocument(
                    opportunity_id=opp_with_links,
                    label="the winner",
                    has_description=True,
                )
            )
            db.commit()
        finally:
            db.close()
        return ([b"LOSER CONTENT"], True)

    monkeypatch.setattr(attachments, "fetch_all", fetch_and_lose_race)
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert r.status_code == 200, f"the race loser must serve the winner: {r.text}"
    assert r.json()["label"] == "the winner"


# --- the fetcher itself --------------------------------------------------------


def test_429_stops_all_downloads(monkeypatch):
    from app.services import http

    calls = {"n": 0}

    def dead_quota(url, **kw):
        calls["n"] += 1
        raise UpstreamError("SAM.gov", "HTTP 429 (rate limited — the API key's request quota is spent)")

    monkeypatch.setattr(http, "get_bytes", dead_quota)
    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "test-key")
    assert attachments.fetch_all(["https://x/1", "https://x/2", "https://x/3"]) == ([], False)
    assert calls["n"] == 1, "a spent daily quota must stop the loop immediately"


def test_dead_link_degrades_per_file(monkeypatch):
    from app.services import http

    def flaky(url, **kw):
        if url.endswith("/1"):
            raise UpstreamError("SAM.gov", "HTTP 404")
        return b"usable text content here"

    monkeypatch.setattr(http, "get_bytes", flaky)
    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "test-key")
    assert attachments.fetch_all(["https://x/1", "https://x/2"]) == (
        [b"usable text content here"],
        True,
    )


def test_unparseable_binary_is_skipped(monkeypatch):
    from app.services import http

    blobs = {
        "https://x/1": b"PK\x03\x04" + bytes(range(256)) * 32,  # a zip
        "https://x/2": b"%PDF-1.7 fake but magic says pdf",
        "https://x/3": b"plain text statement of work",
    }
    monkeypatch.setattr(http, "get_bytes", lambda url, **kw: blobs[url])
    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "test-key")
    out, exhausted = attachments.fetch_all(list(blobs))
    assert exhausted
    assert blobs["https://x/1"] not in out, "binary junk must not poison grounding text"
    assert blobs["https://x/2"] in out and blobs["https://x/3"] in out


def test_corrupt_pdf_degrades_instead_of_500(client, auth_headers, opp_with_links, monkeypatch):
    """PDF magic bytes, garbage body: the parser raises — the document view
    must skip the file and serve the description, not 500 forever."""
    monkeypatch.setattr(
        attachments, "fetch_all", lambda links: ([b"%PDF-1.7 this is not a real pdf body"], True)
    )
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert r.status_code == 200, r.text
    text = "\n".join(s["text"] for s in r.json()["sections"])
    assert "widget maintenance services solicitation" in text


def test_no_key_means_no_fetching(monkeypatch):
    monkeypatch.setattr(config, "SAM_GOV_API_KEY", "")
    assert attachments.fetch_all(["https://x/1"]) == ([], False)


def test_real_pdf_attachment_end_to_end(client, auth_headers, opp_with_links, monkeypatch):
    """A real federal solicitation PDF as the attachment: the served document
    must contain its text as sections the grounding chain can cite."""
    from pathlib import Path

    from app.services import ingest

    samples = sorted(
        Path(__file__).resolve().parent.parent.parent.glob("data/samples/*.pdf"),
        key=lambda p: p.stat().st_size,
    )
    blob = next(
        (
            b
            for p in samples
            if (b := p.read_bytes()) and ingest.pdf_to_text(b).strip()
        ),
        None,
    )
    if blob is None:
        pytest.skip("no text-layer sample PDFs in this checkout")

    monkeypatch.setattr(attachments, "fetch_all", lambda links: ([blob], True))
    r = client.get(f"/opportunities/{opp_with_links}/document", headers=auth_headers)
    assert r.status_code == 200, r.text
    sections = r.json()["sections"]
    pdf_text = "\n".join(
        s["text"] for s in sections if "widget maintenance" not in s["text"]
    )
    if not pdf_text.strip():
        pytest.skip("smallest sample is image-only and OCR is pinned off in tests")
    assert len(pdf_text) > 200, "the PDF's text layer should be in the document"
    assert _doc_row(opp_with_links)[2] == 1


def test_get_bytes_enforces_the_size_cap(monkeypatch):
    import requests as requests_lib

    from app.services import http

    class _FakeResponse:
        ok = True
        status_code = 200

        def iter_content(self, chunk_size):
            while True:
                yield b"x" * chunk_size

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(requests_lib, "get", lambda *a, **kw: _FakeResponse())
    with pytest.raises(UpstreamError) as err:
        http.get_bytes("https://x/big", service="SAM.gov", max_bytes=200_000)
    assert "cap" in str(err.value)
