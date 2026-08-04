"""Auth endpoints: /auth/register and /auth/login.

Local mode (default): bcrypt into `users.password_hash`, short-lived HS256 JWT.

Cognito mode: `/auth/login` proxies the pool's USER_PASSWORD_AUTH flow and
returns the pool-issued **ID token** as `access_token`. The frontend keeps its
exact contract (POST email/password → {access_token, token_type}) while
Cognito owns the passwords — they pass through here over TLS and are never
stored or logged. The ID token (not Cognito's access token) is deliberate:
`current_user` validates `aud` = app client id, which only the ID token
carries. `/auth/register` returns 400 in cognito mode — accounts are created
in the user pool, not here.
"""

import logging

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.auth import create_local_token, hash_password, verify_password
from app.database import get_db
from app.models import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _cognito_login(creds: Credentials) -> TokenResponse:
    """Log in against the Cognito User Pool on the caller's behalf.

    InitiateAuth with USER_PASSWORD_AUTH is an UNSIGNED call — no AWS
    credentials on this server are needed or used, same as a browser would do.
    """
    client = boto3.client(
        "cognito-idp",
        region_name=config.AWS_REGION,
        config=BotoConfig(
            signature_version=UNSIGNED,
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2},
        ),
    )
    try:
        result = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            ClientId=config.COGNITO_APP_CLIENT_ID,
            AuthParameters={"USERNAME": creds.email, "PASSWORD": creds.password},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NotAuthorizedException", "UserNotFoundException"}:
            # Identical message for both — don't reveal which accounts exist.
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid email or password."
            )
        if code == "UserNotConfirmedException":
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Account not confirmed yet — verify the email address first.",
            )
        if code == "PasswordResetRequiredException":
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "A password reset is required for this account.",
            )
        # Anything else (throttling, USER_PASSWORD_AUTH not enabled on the app
        # client, ...) is our problem or AWS's — not the caller's credentials.
        log.warning("Cognito InitiateAuth failed: %s", code or exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Cognito could not process the login ({code or 'unknown error'}).",
        )
    except BotoCoreError as exc:
        log.warning("Cognito unreachable: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Cognito is unreachable right now."
        )

    challenge = result.get("ChallengeName")
    if challenge:
        # e.g. NEW_PASSWORD_REQUIRED when an admin-set temp password was never
        # made permanent. This app has no challenge UI; say what to do instead.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Cognito requires an extra step ({challenge}) this app does not "
            "support — ask an admin to set a permanent password.",
        )
    return TokenResponse(access_token=result["AuthenticationResult"]["IdToken"])


@router.post("/register", response_model=TokenResponse)
def register(creds: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    if config.AUTH_MODE != "local":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Sign-up is managed in the Cognito user pool — ask an admin to "
            "create your account.",
        )
    if len(creds.password) < 10:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Password must be at least 10 characters."
        )
    if db.scalar(select(User).where(User.email == creds.email)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with that email already exists."
        )
    user = User(email=creds.email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_local_token(user))


@router.post("/login", response_model=TokenResponse)
def login(creds: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    if config.AUTH_MODE == "cognito":
        return _cognito_login(creds)
    user = db.scalar(select(User).where(User.email == creds.email))
    # Identical error whether the email is unknown or the password is wrong —
    # don't reveal which accounts exist.
    if user is None or not user.password_hash or not verify_password(
        creds.password, user.password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return TokenResponse(access_token=create_local_token(user))
