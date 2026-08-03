"""Week-2 acceptance, end to end: login -> plan upload -> profile -> document
-> analysis, on LLM_MODE=mock with no AWS.

Asserts response SHAPES against SCHEMA_v2 (exact key sets, not "contains"), so
an added or renamed field fails here before it reaches the frontend.
"""

from __future__ import annotations

# --- auth --------------------------------------------------------------------


def test_login_returns_access_token(client, credentials):
    r = client.post("/auth/login", json=credentials)
    assert r.status_code == 200, r.text
    body = r.json()
    # The exact key the frontend reads. Not `token`, not `jwt`.
    assert "access_token" in body
    assert isinstance(body["access_token"], str) and body["access_token"]


def test_login_rejects_bad_password(client, credentials):
    r = client.post(
        "/auth/login", json={"email": "pytest@rackner.com", "password": "wrong-password"}
    )
    assert r.status_code == 401


def test_login_does_not_reveal_unknown_accounts(client, credentials):
    """Same status and message whether the email exists or not."""
    unknown = client.post(
        "/auth/login", json={"email": "nobody@rackner.com", "password": "wrong-password"}
    )
    wrong = client.post(
        "/auth/login", json={"email": "pytest@rackner.com", "password": "wrong-password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_health_needs_no_auth(client):
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200


def test_protected_routes_require_a_token(client, opportunity_id):
    for path in (
        "/profile",
        f"/opportunities/{opportunity_id}/analysis",
        f"/opportunities/{opportunity_id}/document",
    ):
        assert client.get(path).status_code == 401, path


# --- profile -----------------------------------------------------------------


def test_upload_lifecycle_plan(client, auth_headers):
    plan = b"Capabilities: cloud security.\nNAICS 541512 and 541519.\nWe are a HUBZone firm."
    r = client.post(
        "/profile/lifecycle",
        headers=auth_headers,
        files={"file": ("plan.txt", plan, "text/plain")},
    )
    assert r.status_code == 200, r.text
    lp = r.json()
    assert set(lp) == {
        "filename", "uploaded_at", "capabilities",
        "naics_codes", "target_agencies", "set_asides",
    }
    assert lp["naics_codes"] == ["541512", "541519"]
    assert "HUBZone" in lp["set_asides"]
    assert lp["filename"] == "plan.txt"


def test_empty_upload_is_rejected(client, auth_headers):
    r = client.post(
        "/profile/lifecycle", headers=auth_headers, files={"file": ("e.txt", b"", "text/plain")}
    )
    assert r.status_code == 400


def test_unreadable_upload_is_rejected(client, auth_headers):
    """A scanned-PDF stand-in: no extractable text -> 422, not a silent empty profile."""
    r = client.post(
        "/profile/lifecycle",
        headers=auth_headers,
        files={"file": ("scan.pdf", b"%PDF-1.4\n%garbage", "application/pdf")},
    )
    assert r.status_code == 422


def test_get_profile(client, auth_headers):
    r = client.get("/profile", headers=auth_headers)
    assert r.status_code == 200, r.text
    p = r.json()
    assert set(p) == {"user", "lifecycle"}
    assert set(p["user"]) == {"email", "org", "initials"}
    assert p["user"]["org"] == "rackner.com"
    assert p["lifecycle"] is not None


def test_reupload_replaces_the_plan(client, auth_headers):
    """One active plan per user."""
    plan = b"Capabilities: data engineering.\nNAICS 541511.\n"
    r = client.post(
        "/profile/lifecycle",
        headers=auth_headers,
        files={"file": ("plan-v2.txt", plan, "text/plain")},
    )
    assert r.status_code == 200
    p = client.get("/profile", headers=auth_headers).json()
    assert p["lifecycle"]["filename"] == "plan-v2.txt"
    assert p["lifecycle"]["naics_codes"] == ["541511"]


# --- document ----------------------------------------------------------------


def test_get_document(client, auth_headers, opportunity_id, solicitation):
    r = client.get(f"/opportunities/{opportunity_id}/document", headers=auth_headers)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert set(doc) == {"opportunity_id", "label", "sections"}
    secs = doc["sections"]
    assert len(secs) >= 3
    assert all(set(s) == {"ref", "heading", "text", "page"} for s in secs)
    refs = [s["ref"] for s in secs]
    assert "C.3.1" in refs and "252.204-7012" in refs
    assert all(not s["ref"].startswith("§") for s in secs)
    # Sections are slices of the CANONICAL text (ingest normalizes smart
    # punctuation at the boundary), not of the raw input string.
    from app.services.ingest import canonicalize

    assert all(s["text"] in canonicalize(solicitation) for s in secs)


def test_document_is_stable_across_requests(client, auth_headers, opportunity_id):
    """Re-parsing on read could yield text the quotes weren't verified against."""
    a = client.get(f"/opportunities/{opportunity_id}/document", headers=auth_headers).json()
    b = client.get(f"/opportunities/{opportunity_id}/document", headers=auth_headers).json()
    assert a == b


def test_unknown_opportunity_is_404(client, auth_headers):
    assert client.get("/opportunities/NOPE/document", headers=auth_headers).status_code == 404
    assert client.get("/opportunities/NOPE/analysis", headers=auth_headers).status_code == 404


# --- analysis ----------------------------------------------------------------


def test_analysis_shape(client, auth_headers, opportunity_id):
    r = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers)
    assert r.status_code == 200, r.text
    a = r.json()
    assert set(a) == {"opportunity_id", "score", "band", "verdict", "factors", "obligations"}
    assert "compatibility_score" not in a
    assert 0 <= a["score"] <= 100
    assert a["band"] in ("pursue", "conditional", "no_bid")
    # `verdict` is prose in v2, NOT the enum.
    assert isinstance(a["verdict"], str)
    assert a["verdict"] not in ("pursue", "conditional", "no_bid")


def test_analysis_factors(client, auth_headers, opportunity_id):
    a = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers).json()
    factors = a["factors"]
    assert len(factors) == 8
    assert all(
        set(f) == {"key", "label", "weight", "score", "rationale", "citation"} for f in factors
    )
    assert all(1 <= f["score"] <= 5 for f in factors)
    assert abs(sum(f["weight"] for f in factors) - 1.0) < 1e-9
    assert all(f["rationale"] for f in factors), "rationale is required"


def test_analysis_obligations(client, auth_headers, opportunity_id):
    a = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers).json()
    obs = a["obligations"]
    assert obs, "expected at least one obligation"
    assert all(
        set(o) == {
            "id", "text", "obligation_type", "time_bucket",
            "deadline_label", "verbatim_quote", "citation", "verified",
        }
        for o in obs
    )
    assert len({o["id"] for o in obs}) == len(obs), "obligation ids must be unique"
    assert all(set(o["citation"]) == {"section", "page"} for o in obs)
    assert all(
        o["time_bucket"]
        in {"immediate", "30_days", "at_award", "quarterly", "ongoing", "unclear"}
        for o in obs
    )


def test_band_agrees_with_score(client, auth_headers, opportunity_id):
    from app.schemas import band_for

    a = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers).json()
    assert a["band"] == band_for(a["score"])


def test_analysis_is_cached(client, auth_headers, opportunity_id):
    a = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers).json()
    b = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers).json()
    assert a == b


def test_verified_quotes_are_highlightable_over_http(client, auth_headers, opportunity_id):
    """The end-to-end contract, across the wire this time.

    Every verified obligation from GET /analysis must be findable by indexOf in
    the section GET /document serves under the ref its citation names.
    """
    a = client.get(f"/opportunities/{opportunity_id}/analysis", headers=auth_headers).json()
    doc = client.get(f"/opportunities/{opportunity_id}/document", headers=auth_headers).json()
    by_ref = {s["ref"]: s["text"] for s in doc["sections"]}

    verified = [o for o in a["obligations"] if o["verified"]]
    assert verified, "expected at least one verified obligation"
    for o in verified:
        cited = by_ref.get(o["citation"]["section"])
        assert cited is not None, f"citation names a section not in the document: {o['citation']}"
        assert cited.find(o["verbatim_quote"]) != -1, (
            f"UI indexOf would fail for {o['verbatim_quote']!r}"
        )


# --- LLM harness routes -------------------------------------------------------


def test_llm_extract(client, auth_headers, solicitation):
    r = client.post("/llm/extract", headers=auth_headers, json={"chunk_text": solicitation})
    assert r.status_code == 200, r.text
    obs = r.json()
    assert obs
    assert all(o["verified"] for o in obs), "quotes from the chunk itself must verify"


def test_llm_status(client, auth_headers):
    body = client.get("/llm/status", headers=auth_headers).json()
    assert body["llm_mode"] == "mock"
    assert body["auth_mode"] == "local"


# --- CORS ---------------------------------------------------------------------


def test_cors_preflight_from_next_dev_origin(client):
    """The first thing that breaks if ALLOWED_ORIGINS is wrong."""
    r = client.options(
        "/profile",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
