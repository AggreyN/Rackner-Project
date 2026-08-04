"""Week-4 hardening: secrets fallback, log redaction, JWKS rotation, request id.

The prod halves of these (real Secrets Manager, real Cognito pool, CloudWatch)
need provisioned AWS and are exercised by flipping env vars per the Dev→prod
table. What CAN be tested offline is the contract each abstraction promises:
dev fallback works, secrets never reach a log line, key rotation doesn't lock
users out, and every response is joinable to its log line.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.logging_config import JsonFormatter
from app.services import secrets


# --- secrets ------------------------------------------------------------------


def test_dev_reads_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("SOME_SECRET", "from-env")
    assert secrets.get_secret("SOME_SECRET", "default") == "from-env"


def test_dev_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    assert secrets.get_secret("MISSING_SECRET", "the-default") == "the-default"


def test_dev_never_calls_aws(monkeypatch):
    """Importing boto3 in dev mode would mean a network call path exists."""
    monkeypatch.setenv("APP_ENV", "dev")

    def explode(name):
        raise AssertionError("Secrets Manager must not be consulted in dev")

    monkeypatch.setattr(secrets, "_from_secrets_manager", explode)
    assert secrets.get_secret("ANYTHING", "d") == "d"


def test_prod_prefers_secrets_manager(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DB_URL_TEST", "from-env")
    monkeypatch.setattr(secrets, "_from_secrets_manager", lambda name: "from-asm")
    assert secrets.get_secret("DB_URL_TEST", "default") == "from-asm"


def test_prod_falls_back_to_env_when_asm_unavailable(monkeypatch):
    """The ECS pattern: the task definition injects the secret AS an env var.
    A Secrets Manager miss must fall through, not crash boot."""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("INJECTED_SECRET", "from-task-definition")
    monkeypatch.setattr(secrets, "_from_secrets_manager", lambda name: None)
    assert secrets.get_secret("INJECTED_SECRET", "default") == "from-task-definition"


def test_secrets_manager_lookups_are_cached(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    calls = {"n": 0}

    class FakeClient:
        def get_secret_value(self, SecretId):
            calls["n"] += 1
            return {"SecretString": "cached-value"}

    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeClient())
    secrets._cache.clear()
    try:
        assert secrets.get_secret("CACHE_TEST") == "cached-value"
        assert secrets.get_secret("CACHE_TEST") == "cached-value"
        assert calls["n"] == 1, "second read must come from the cache"
    finally:
        secrets._cache.clear()


# --- log redaction ------------------------------------------------------------


def _format(**fields) -> dict:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", (), None)
    for key, value in fields.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


@pytest.mark.parametrize(
    "field",
    ["authorization", "Authorization", "access_token", "token", "jwt", "password", "api_key"],
)
def test_secretish_fields_are_redacted(field):
    entry = _format(**{field: "hunter2-super-secret"})
    assert entry[field] == "[REDACTED]"
    assert "hunter2" not in json.dumps(entry)


def test_ordinary_fields_pass_through():
    entry = _format(request_id="abc123", status=200, latency_ms=12.5)
    assert entry["request_id"] == "abc123"
    assert entry["status"] == 200


def test_output_is_valid_json_per_line():
    entry = _format(route="/profile", user_sub="u-1")
    assert entry["message"] == "msg"
    assert entry["level"] == "INFO"


# --- request id ---------------------------------------------------------------


def test_every_response_carries_a_request_id(client):
    r = client.get("/health")
    assert r.headers.get("x-request-id"), "responses must be joinable to log lines"


def test_request_ids_are_unique_per_request(client):
    a = client.get("/health").headers["x-request-id"]
    b = client.get("/health").headers["x-request-id"]
    assert a != b


# --- JWKS rotation ------------------------------------------------------------


def test_unknown_kid_triggers_one_forced_jwks_refetch(monkeypatch):
    """Cognito key rotation: a token signed by a NEW key must trigger a cache
    refresh rather than 401ing until the hourly expiry."""
    from app import auth

    fetches = {"n": 0}
    old = [{"kid": "old-key"}]
    new = [{"kid": "old-key"}, {"kid": "new-key"}]

    def fake_get_jwks(*, force_refresh: bool = False):
        fetches["n"] += 1
        return new if force_refresh else old

    monkeypatch.setattr(auth, "_get_jwks", fake_get_jwks)

    key = auth._key_for("new-key")
    assert key == {"kid": "new-key"}
    assert fetches["n"] == 2, "expected exactly one cached read + one forced refetch"


def test_known_kid_uses_the_cache_only(monkeypatch):
    from app import auth

    fetches = {"n": 0}

    def fake_get_jwks(*, force_refresh: bool = False):
        fetches["n"] += 1
        assert not force_refresh, "cache hit must not force a refetch"
        return [{"kid": "current"}]

    monkeypatch.setattr(auth, "_get_jwks", fake_get_jwks)
    assert auth._key_for("current") == {"kid": "current"}
    assert fetches["n"] == 1


def test_truly_unknown_kid_is_rejected_after_refetch(monkeypatch):
    from app import auth

    monkeypatch.setattr(
        auth, "_get_jwks", lambda *, force_refresh=False: [{"kid": "only-key"}]
    )
    assert auth._key_for("forged-kid") is None


# --- database pool config -----------------------------------------------------


def test_sqlite_gets_no_pool_knobs():
    from app.database import _engine_kwargs

    assert _engine_kwargs("sqlite:///x.db") == {}


def test_postgres_gets_pre_ping_and_bounded_pool():
    from app.database import _engine_kwargs

    kwargs = _engine_kwargs("postgresql+psycopg://h/db")
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_size"] >= 1
    assert kwargs["pool_recycle"] <= 3600


# --- 429 fails fast -----------------------------------------------------------


def test_429_is_not_retried(monkeypatch):
    """A daily-quota 429 cannot clear inside a 4s backoff. Retrying it three
    times turned a fast failure into a measured 47-51s hang. One attempt, then
    a clean UpstreamError naming the quota."""
    import requests as requests_lib

    from app.services import http as http_mod

    calls = {"n": 0}

    class Fake429:
        status_code = 429
        ok = False
        text = "rate limited"

    def fake_request(method, url, timeout=None, **kwargs):
        calls["n"] += 1
        return Fake429()

    monkeypatch.setattr(requests_lib, "request", fake_request)
    import pytest as _pytest

    with _pytest.raises(http_mod.UpstreamError) as exc:
        http_mod.get_json("https://example.invalid/x", service="SAM.gov")
    assert calls["n"] == 1, f"429 was retried {calls['n']} times; it must fail fast"
    assert "rate limited" in str(exc.value)


def test_5xx_is_still_retried(monkeypatch):
    import requests as requests_lib

    from app.services import http as http_mod

    calls = {"n": 0}

    class Fake502:
        status_code = 502
        ok = False
        text = "bad gateway"

    monkeypatch.setattr(
        requests_lib, "request", lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), Fake502())[1]
    )
    import pytest as _pytest

    with _pytest.raises(http_mod.UpstreamError):
        http_mod.get_json("https://example.invalid/x", service="USAspending.gov")
    assert calls["n"] == 3, f"5xx should retry (3 attempts), got {calls['n']}"
