"""Local-mode auth endpoints: /auth/register and /auth/login.

These exist for the bcrypt demo path (AUTH_MODE=local). In Cognito mode the
frontend authenticates against the User Pool directly, so these return 400.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.auth import create_local_token, hash_password, verify_password
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _require_local_mode() -> None:
    if config.AUTH_MODE != "local":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Local auth is disabled (AUTH_MODE=cognito). Authenticate via Cognito.",
        )


@router.post("/register", response_model=TokenResponse)
def register(creds: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    _require_local_mode()
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
    _require_local_mode()
    user = db.scalar(select(User).where(User.email == creds.email))
    # Identical error whether the email is unknown or the password is wrong —
    # don't reveal which accounts exist.
    if user is None or not user.password_hash or not verify_password(
        creds.password, user.password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return TokenResponse(access_token=create_local_token(user))
