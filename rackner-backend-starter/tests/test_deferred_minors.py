"""Regressions for the deferred audit-2 minors (fixed 2026-08-21).

Each test pins one of the small-but-real defects the round-2 adversarial
audit confirmed and we deferred past the production-handoff ship:

  * compatibility_score assumed factor weights sum to 1.0 — a partial
    factor set (the gateway drops malformed factors) produced nonsense
    scores that then persisted permanently.
  * analyze() persisted a factor-less row when the model misbehaved badly
    enough that every factor was dropped.
  * An unknown JWT kid triggered an unthrottled Cognito JWKS refetch —
    an unauthenticated hammer-Cognito vector.
  * Email guessing flipped "Last, First" POC names (doe.jane@ for Jane
    Doe) and treated generational suffixes as surnames.
  * active_solicitation was `bool(close_date)` — notices whose deadline
    passed months ago flagged "outreach constrained" forever.
"""

from __future__ import annotations

import datetime
import time

import pytest

from app import auth, config
from app.database import SessionLocal
from app.llm import gateway
from app.models import Analysis, Opportunity, SourceDocument
from app.routes import documents
from app.schemas import FitFactor, compatibility_score
from app.services import attachments, email_discovery


def _factor(weight: float, score: int, key: str = "technical_capability") -> FitFactor:
    return FitFactor(
        key=key, label=key, weight=weight, score=score, rationale="test rationale"
    )


class TestWeightsNormalization:
    def test_full_set_unchanged(self):
        # Eight well-formed factors whose weights sum to 1.0 — the normal
        # case must score exactly as before the normalization change.
        weights = [0.20, 0.15, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10]
        factors = [_factor(w, 4, key=f"f{i}") for i, w in enumerate(weights)]
        assert compatibility_score(factors) == 75.0  # (4-1)/4 * 100

    def test_partial_set_is_scaled_not_garbage(self):
        # One surviving 0.2-weight factor scoring 3/5 used to yield -10.
        assert compatibility_score([_factor(0.2, 3)]) == 50.0

    def test_duplicated_factors_cannot_exceed_100(self):
        factors = [_factor(0.2, 5, key=f"dup{i}") for i in range(10)]
        assert compatibility_score(factors) == 100.0

    def test_empty_or_zero_weight_set_scores_zero(self):
        assert compatibility_score([]) == 0.0
        assert compatibility_score([_factor(0.0, 5)]) == 0.0


def test_analyze_raises_instead_of_persisting_factorless_row(monkeypatch):
    # Mock mode returns well-formed factors; force them all malformed so the
    # normalizer drops everything — analyze must fail the generation rather
    # than hand back a permanent 0-score row.
    monkeypatch.setattr(
        gateway.mock,
        "analyze_factors",
        lambda opp, prof: {"factors": [{"weight": 2.0}], "verdict_note": "x"},
    )
    with pytest.raises(RuntimeError, match="no usable fit factors"):
        gateway.analyze({"id": "x"}, {}, sections=[])


def test_analyze_raises_on_all_zero_weight_factors(monkeypatch):
    # Well-formed factors whose weights are ALL zero slip past the empty
    # check but would score 0.0 just as meaninglessly — same raise.
    zero = {
        "key": "technical_capability", "label": "Tech", "weight": 0.0,
        "score": 4, "rationale": "r",
    }
    monkeypatch.setattr(
        gateway.mock,
        "analyze_factors",
        lambda opp, prof: {"factors": [zero, dict(zero, key="mission_alignment")],
                           "verdict_note": "x"},
    )
    with pytest.raises(RuntimeError, match="no usable fit factors"):
        gateway.analyze({"id": "x"}, {}, sections=[])


def test_unusable_generation_is_a_named_502_not_a_bare_500(
    client, auth_headers, monkeypatch
):
    """A bare 500 bypasses CORS (the browser can't read it); the route must
    name the failure. 502 — a non-outage 503 would read as "generating"."""
    opp_id = "UNUSABLE-GEN-1"
    db = SessionLocal()
    try:
        if db.get(Opportunity, opp_id) is None:
            db.add(Opportunity(id=opp_id, title="t", agency="a",
                               description="Some grounding text."))
            db.commit()
        db.query(Analysis).filter_by(opportunity_id=opp_id).delete()
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(
        gateway.mock,
        "analyze_factors",
        lambda opp, prof: {"factors": [{"weight": 2.0}], "verdict_note": "x"},
    )
    r = client.get(f"/opportunities/{opp_id}/analysis", headers=auth_headers)
    assert r.status_code == 502
    assert "unusable" in r.json()["detail"]
    db = SessionLocal()
    try:
        assert (
            db.query(Analysis).filter_by(opportunity_id=opp_id).count() == 0
        ), "nothing may be cached for a failed generation"
    finally:
        db.close()


class TestJwksMissThrottle:
    def _reset(self):
        auth._jwks_cache.update(
            {"keys": [{"kid": "known"}], "fetched_at": 0.0, "miss_refetch_at": None}
        )

    def test_known_kid_never_refetches(self, monkeypatch):
        self._reset()
        auth._jwks_cache["fetched_at"] = time.monotonic()
        calls = {"forced": 0}

        def fake_get_jwks(*, force_refresh: bool = False):
            if force_refresh:
                calls["forced"] += 1
            return [{"kid": "known"}]

        monkeypatch.setattr(auth, "_get_jwks", fake_get_jwks)
        assert auth._key_for("known") == {"kid": "known"}
        assert calls["forced"] == 0

    def test_bogus_kid_spam_refetches_once_per_cooldown(self, monkeypatch):
        self._reset()
        calls = {"forced": 0}

        def fake_get_jwks(*, force_refresh: bool = False):
            if force_refresh:
                calls["forced"] += 1
            return [{"kid": "known"}]

        monkeypatch.setattr(auth, "_get_jwks", fake_get_jwks)
        for _ in range(25):
            assert auth._key_for("bogus") is None
        assert calls["forced"] == 1

    def test_rotation_lands_on_first_miss(self, monkeypatch):
        self._reset()

        def fake_get_jwks(*, force_refresh: bool = False):
            return [{"kid": "rotated"}] if force_refresh else [{"kid": "old"}]

        monkeypatch.setattr(auth, "_get_jwks", fake_get_jwks)
        assert auth._key_for("rotated") == {"kid": "rotated"}

    def test_concurrent_rotation_misses_all_resolve(self, monkeypatch):
        """During a real rotation a page fires several requests at once; the
        first through the lock refetches and the rest must find the rotated
        key on their re-check — not 401 the user into a forced logout."""
        import threading

        self._reset()
        auth._jwks_cache["keys"] = [{"kid": "old"}]
        auth._jwks_cache["fetched_at"] = time.monotonic()

        def fake_get_jwks(*, force_refresh: bool = False):
            if force_refresh:
                time.sleep(0.2)  # a slow Cognito fetch, held under the lock
                auth._jwks_cache["keys"] = [{"kid": "rotated"}]
            return auth._jwks_cache["keys"]

        monkeypatch.setattr(auth, "_get_jwks", fake_get_jwks)
        results: list = []
        threads = [
            threading.Thread(target=lambda: results.append(auth._key_for("rotated")))
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results == [{"kid": "rotated"}] * 4


class TestNameParsing:
    def test_last_comma_first_swaps(self):
        assert email_discovery._split_name("Doe, Jane") == ("jane", "", "doe")

    def test_last_comma_first_middle(self):
        assert email_discovery._split_name("Doe, Jane Ann") == ("jane", "ann", "doe")

    def test_natural_order_untouched(self):
        assert email_discovery._split_name("Jane Doe") == ("jane", "", "doe")

    def test_suffix_is_not_a_surname(self):
        assert email_discovery._split_name("John Doe Jr.") == ("john", "", "doe")

    def test_single_letter_first_initial_is_not_a_suffix(self):
        # "Patel, V" — the 'v' is a first initial, not "the fifth"; stripping
        # it left no first name and 404'd the whole contact.
        assert email_discovery._split_name("Patel, V") == ("v", "", "patel")

    def test_comma_name_guesses_natural_pattern(self):
        guesses = email_discovery.candidates("Doe, Jane", "example.mil")
        assert guesses[0][0] == "jane.doe@example.mil"


class TestActiveSolicitation:
    def test_future_close_date_is_active(self):
        opp = {"close_date": datetime.date.today() + datetime.timedelta(days=10)}
        assert email_discovery._solicitation_open(opp) is True

    def test_past_close_date_is_not_active(self):
        opp = {"close_date": datetime.date.today() - datetime.timedelta(days=10)}
        assert email_discovery._solicitation_open(opp) is False

    def test_isoformat_string_close_date(self):
        past = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
        assert email_discovery._solicitation_open({"close_date": past}) is False

    def test_expiring_award_never_active(self):
        opp = {
            "kind": "expiring_award",
            "close_date": datetime.date.today() + datetime.timedelta(days=10),
        }
        assert email_discovery._solicitation_open(opp) is False

    def test_unparseable_close_date_stays_conservative(self):
        assert email_discovery._solicitation_open({"close_date": "TBD"}) is True

    def test_cached_contact_row_recomputes_flag_at_serve_time(
        self, client, auth_headers
    ):
        # Contact rows cache forever, so the stored flag freezes at first
        # discovery — serving must derive from the opportunity's CURRENT
        # close date, or a long-closed notice warns about outreach forever.
        from app.models import Contact

        opp_id = "STALE-CONTACT-1"
        db = SessionLocal()
        try:
            row = db.get(Opportunity, opp_id)
            if row is None:
                row = Opportunity(id=opp_id, title="t", agency="a")
                db.add(row)
            row.close_date = datetime.date.today() - datetime.timedelta(days=30)
            db.query(Contact).filter_by(opportunity_id=opp_id).delete()
            db.add(Contact(opportunity_id=opp_id, name="Jane Doe",
                           title="CO", office="o", email="jane@x.mil",
                           confidence=0.9, active_solicitation=True))
            db.commit()
        finally:
            db.close()
        r = client.get(f"/opportunities/{opp_id}/contact", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["active_solicitation"] is False


def _seed_backoff_opp(opp_id: str, links: list[str]) -> None:
    db = SessionLocal()
    try:
        row = db.get(Opportunity, opp_id)
        if row is None:
            row = Opportunity(id=opp_id, title="Backoff target", agency="DoD")
            db.add(row)
        row.description = "Summary: services solicitation with attachments."
        row.resource_links = links
        for doc in db.query(SourceDocument).filter_by(opportunity_id=opp_id):
            db.delete(doc)
        db.query(Analysis).filter_by(opportunity_id=opp_id).delete()
        db.commit()
    finally:
        db.close()


def test_failed_attachment_pass_backs_off_instead_of_rebilling_every_read(
    client, auth_headers, monkeypatch
):
    """One dead-host link used to make EVERY document read re-download (and
    re-bill) all attachments. A not-exhausted pass now suppresses further
    passes for a TTL; expiry, new links, and an exhausted pass all end it."""
    opp_id = "BACKOFF-1"
    _seed_backoff_opp(opp_id, ["https://x/good", "https://x/dead-host"])
    monkeypatch.setattr(config, "ATTACHMENT_RETRY_BACKOFF_MINUTES", 15.0)

    calls = {"n": 0}

    def one_good_one_transient(links):
        calls["n"] += 1
        return ([b"GOOD ATTACHMENT TEXT"], False)  # dead link stays unresolved

    monkeypatch.setattr(attachments, "fetch_all", one_good_one_transient)
    for _ in range(3):
        r = client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
        assert r.status_code == 200
    assert calls["n"] == 1, "reads inside the backoff window must not re-bill"

    # Retry INTENT survives in the DB: accounted stays below the link count.
    db = SessionLocal()
    try:
        doc = db.query(SourceDocument).filter_by(opportunity_id=opp_id).one()
        assert (doc.attachments_accounted or 0) < 2
    finally:
        db.close()

    # TTL expiry re-allows a pass — the audit-1 permanent-give-up bug must
    # not recur.
    deadline, seen = documents._fetch_backoff[opp_id]
    documents._fetch_backoff[opp_id] = (time.monotonic(), seen)
    client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    assert calls["n"] == 2

    # Links added since the failed pass break through immediately.
    _seed_backoff_opp_links_grow = ["https://x/good", "https://x/dead-host", "https://x/new"]
    db = SessionLocal()
    try:
        db.get(Opportunity, opp_id).resource_links = _seed_backoff_opp_links_grow
        db.commit()
    finally:
        db.close()
    client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    assert calls["n"] == 3

    # An exhausted pass clears the memo and resolves everything; after it,
    # reads cost zero passes again.
    deadline, seen = documents._fetch_backoff[opp_id]
    documents._fetch_backoff[opp_id] = (time.monotonic(), seen)
    monkeypatch.setattr(
        attachments,
        "fetch_all",
        lambda links: ([b"GOOD ATTACHMENT TEXT", b"SECOND TEXT NOW"], True),
    )
    client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    assert opp_id not in documents._fetch_backoff
    before = calls["n"]
    monkeypatch.setattr(attachments, "fetch_all", one_good_one_transient)
    client.get(f"/opportunities/{opp_id}/document", headers=auth_headers)
    assert calls["n"] == before, "fully-resolved docs must not fetch at all"
