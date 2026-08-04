"""Cognito-mode /auth/login proxy — offline, boto3 faked.

The real pool path is proven in test_cognito_live.py. These pin the contract
the frontend depends on: same request/response shape as local mode, the ID
token (never Cognito's access token) returned as `access_token`, bad-user and
bad-password indistinguishable, and non-credential failures surfacing as 503 —
never a 500.
"""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app import config
from app.routes import auth as auth_routes


class _FakeCognito:
    def __init__(self, outcome):
        self._outcome = outcome

    def initiate_auth(self, **kwargs):
        assert kwargs["AuthFlow"] == "USER_PASSWORD_AUTH"
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeBoto:
    def __init__(self, outcome):
        self._outcome = outcome

    def client(self, *args, **kwargs):
        return _FakeCognito(self._outcome)


@pytest.fixture()
def cognito_mode(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "cognito")


def _rig(monkeypatch, outcome):
    monkeypatch.setattr(auth_routes, "boto3", _FakeBoto(outcome))


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "InitiateAuth")


def test_login_returns_the_pool_id_token(client, cognito_mode, monkeypatch):
    """The ID token — current_user checks `aud`, which access tokens lack."""
    _rig(
        monkeypatch,
        {"AuthenticationResult": {"IdToken": "id-token-xyz", "AccessToken": "access-token-abc"}},
    )
    r = client.post(
        "/auth/login", json={"email": "demo@rackner.com", "password": "pw-123456789"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] == "id-token-xyz"
    assert body["token_type"] == "bearer"


def test_wrong_password_and_unknown_user_are_indistinguishable(
    client, cognito_mode, monkeypatch
):
    details = set()
    for code in ("NotAuthorizedException", "UserNotFoundException"):
        _rig(monkeypatch, _client_error(code))
        r = client.post("/auth/login", json={"email": "a@b.com", "password": "nope-nope-1"})
        assert r.status_code == 401
        details.add(r.json()["detail"])
    assert len(details) == 1, "both failures must return the identical message"


def test_unconfirmed_account_gets_a_helpful_401(client, cognito_mode, monkeypatch):
    _rig(monkeypatch, _client_error("UserNotConfirmedException"))
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "pw-123456789"})
    assert r.status_code == 401
    assert "confirm" in r.json()["detail"].lower()


def test_cognito_outage_is_503_not_500(client, cognito_mode, monkeypatch):
    _rig(monkeypatch, EndpointConnectionError(endpoint_url="https://cognito-idp"))
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "pw-123456789"})
    assert r.status_code == 503


def test_misconfigured_auth_flow_is_503_not_500(client, cognito_mode, monkeypatch):
    """USER_PASSWORD_AUTH disabled on the app client is OUR misconfiguration,
    not the caller's credentials — it must not read as a wrong password."""
    _rig(monkeypatch, _client_error("InvalidParameterException"))
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "pw-123456789"})
    assert r.status_code == 503
    assert "InvalidParameterException" in r.json()["detail"]


def test_challenge_is_a_401_with_guidance(client, cognito_mode, monkeypatch):
    _rig(monkeypatch, {"ChallengeName": "NEW_PASSWORD_REQUIRED"})
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "pw-123456789"})
    assert r.status_code == 401
    assert "NEW_PASSWORD_REQUIRED" in r.json()["detail"]


def test_register_is_disabled_in_cognito_mode(client, cognito_mode):
    r = client.post(
        "/auth/register", json={"email": "new@x.com", "password": "Long-enough-1!"}
    )
    assert r.status_code == 400
    assert "Cognito" in r.json()["detail"]
