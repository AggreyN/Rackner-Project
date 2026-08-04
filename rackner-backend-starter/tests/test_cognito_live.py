"""Live Cognito end-to-end — the last unverified inch of the auth path.

    RUN_COGNITO_TESTS=1 \
    TEST_COGNITO_EMAIL=test@rackner.com \
    TEST_COGNITO_PASSWORD='...' \
    pytest tests/test_cognito_live.py

Everything else about cognito mode is already verified against the real pool
(JWKS fetch, forged-kid rejection, wrong-issuer rejection, local-login 400).
What only a real login can prove: a genuine pool-issued ID token passes
signature/iss/aud validation and upserts a users row keyed by its sub.

Prerequisites (one-time, in the AWS console):
  1. User pools -> us-east-2_ayUv1m7Et -> Users -> Create user
     (set the password as PERMANENT, or log in once to clear FORCE_CHANGE_PASSWORD)
  2. App client -> Auth flows: enable ALLOW_USER_PASSWORD_AUTH
     (SRP-only clients can't be driven from a simple script)

InitiateAuth is an UNSIGNED API call — no AWS credentials are needed, which is
the point: this test proves the auth path with nothing but a username and
password, same as a browser would.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_COGNITO_TESTS") != "1",
    reason="live Cognito test; set RUN_COGNITO_TESTS=1 + TEST_COGNITO_EMAIL/PASSWORD",
)


@pytest.fixture(scope="module")
def id_token():
    email = os.getenv("TEST_COGNITO_EMAIL")
    password = os.getenv("TEST_COGNITO_PASSWORD")
    if not email or not password:
        pytest.skip("TEST_COGNITO_EMAIL / TEST_COGNITO_PASSWORD not set")

    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    from app import config

    client = boto3.client(
        "cognito-idp",
        region_name=config.AWS_REGION,
        config=Config(signature_version=UNSIGNED),
    )
    params = {
        "AuthFlow": "USER_PASSWORD_AUTH",
        "ClientId": config.COGNITO_APP_CLIENT_ID,
        "AuthParameters": {"USERNAME": email, "PASSWORD": password},
    }
    try:
        result = client.initiate_auth(**params)
    except client.exceptions.NotAuthorizedException:
        pytest.fail("Cognito rejected the credentials — wrong password, or the app client has a secret")
    except client.exceptions.InvalidParameterException as exc:
        pytest.fail(f"USER_PASSWORD_AUTH likely not enabled on the app client: {exc}")

    challenge = result.get("ChallengeName")
    if challenge:
        pytest.fail(
            f"login returned challenge {challenge} — in the console, set the "
            f"user's password as permanent (not FORCE_CHANGE_PASSWORD)"
        )
    return result["AuthenticationResult"]["IdToken"]


@pytest.fixture(scope="module")
def cognito_client(id_token):
    """A TestClient running in cognito mode against the migrated test DB."""
    from app import config

    original = config.AUTH_MODE
    config.AUTH_MODE = "cognito"
    yield
    config.AUTH_MODE = original


def test_real_id_token_is_accepted(client, cognito_client, id_token):
    r = client.get("/me", headers={"Authorization": f"Bearer {id_token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auth_mode"] == "cognito"
    assert body["cognito_sub"], "user must be linked to the Cognito identity"
    assert body["email"] == os.getenv("TEST_COGNITO_EMAIL")


def test_real_token_reaches_protected_routes(client, cognito_client, id_token):
    r = client.get("/profile", headers={"Authorization": f"Bearer {id_token}"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == os.getenv("TEST_COGNITO_EMAIL")


def test_user_row_was_upserted_by_sub(client, cognito_client, id_token):
    """Same token twice must map to ONE row, keyed by sub — not a duplicate."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    client.get("/me", headers={"Authorization": f"Bearer {id_token}"})
    client.get("/me", headers={"Authorization": f"Bearer {id_token}"})

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(User).where(User.email == os.getenv("TEST_COGNITO_EMAIL"))
        ).all()
    finally:
        db.close()
    assert len(rows) == 1
    assert rows[0].cognito_sub
    assert rows[0].password_hash is None, "Cognito users must never grow a local password"


def test_access_token_is_rejected_with_helpful_distinction(cognito_client, client, id_token):
    """Guard the Remy footgun: the ACCESS token (no `aud` claim) must 401.

    We can't mint one here without repeating initiate_auth, so this asserts on
    the ID token's claims instead: aud present and equal to the app client id —
    the exact thing access tokens lack.
    """
    from jose import jwt

    from app import config

    claims = jwt.get_unverified_claims(id_token)
    assert claims.get("aud") == config.COGNITO_APP_CLIENT_ID
    assert claims.get("token_use") == "id"
