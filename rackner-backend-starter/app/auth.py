"""Authentication — Amazon Cognito (primary) with a local bcrypt fallback (demo).

Two modes, selected by `AUTH_MODE` in config:

- **cognito**: the frontend logs in against a Cognito User Pool and sends the
  Cognito-issued JWT. We validate that JWT against the pool's public JWKS
  (checking signature, issuer, audience, expiry) and upsert a `users` row keyed
  by the token's `sub`. Passwords never touch this service — Cognito owns them.

- **local** (default): no AWS needed. `/auth/register` and `/auth/login`
  (routes/auth.py) hash passwords with bcrypt into `users.password_hash` and
  hand back a short-lived HS256 JWT we sign ourselves. This is the "secure
  password storage (bcrypt)" path for demos before Cognito is wired up.

`current_user` is the one dependency routes use; it does the right thing for
whichever mode is active.
"""

import time

import requests
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False so we can raise our own 401 (with a WWW-Authenticate header).
_bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# Local mode — password hashing + our own JWT
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_local_token(user: User) -> str:
    """Sign a short-lived HS256 token for a local-mode user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def _user_from_local_token(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(
            token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists.")
    return user


# --------------------------------------------------------------------------- #
# Cognito mode — validate the pool's JWT against its JWKS
# --------------------------------------------------------------------------- #
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


def _get_jwks() -> list[dict]:
    """Fetch and cache (1h) the Cognito User Pool's public signing keys."""
    if not config.COGNITO_JWKS_URL:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "AUTH_MODE=cognito but COGNITO_USER_POOL_ID is not configured.",
        )
    if _jwks_cache["keys"] is None or (time.monotonic() - _jwks_cache["fetched_at"]) > 3600:
        resp = requests.get(config.COGNITO_JWKS_URL, timeout=5)
        resp.raise_for_status()
        _jwks_cache["keys"] = resp.json()["keys"]
        _jwks_cache["fetched_at"] = time.monotonic()
    return _jwks_cache["keys"]


def _verify_cognito_token(token: str) -> dict:
    """Validate a Cognito ID token: signature (RS256), issuer, audience, expiry."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token header.")

    key = next((k for k in _get_jwks() if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signing key not found in JWKS.")

    try:
        # Cognito ID tokens carry `aud` = app client id and `iss` = the pool URL.
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=config.COGNITO_APP_CLIENT_ID,
            issuer=config.COGNITO_ISSUER,
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token validation failed: {exc}")


def _upsert_cognito_user(claims: dict, db: Session) -> User:
    """Find-or-create the local `users` row for a validated Cognito identity."""
    sub = claims["sub"]
    email = claims.get("email", "") or f"{sub}@cognito.local"

    user = db.scalar(select(User).where(User.cognito_sub == sub))
    if user is None:
        # First time we've seen this Cognito user — link by email if we can.
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, cognito_sub=sub)
            db.add(user)
        else:
            user.cognito_sub = sub
        db.commit()
        db.refresh(user)
    return user


# --------------------------------------------------------------------------- #
# The dependency every protected route uses
# --------------------------------------------------------------------------- #
def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user for whichever AUTH_MODE is active."""
    if creds is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = creds.credentials
    if config.AUTH_MODE == "cognito":
        return _upsert_cognito_user(_verify_cognito_token(token), db)
    return _user_from_local_token(token, db)
