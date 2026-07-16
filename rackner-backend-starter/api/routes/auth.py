"""Auth endpoints — only mounted when AUTH_ENABLED=true (see api/main.py).

Keeps credential handling in one reviewable place. Passwords are bcrypt-hashed
(core/security.py); plaintext is never stored or logged.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from core.security import hash_password, verify_password, create_token
from db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(creds: Credentials, db: Session = Depends(get_db)):
    if len(creds.password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters.")
    if db.scalar(select(User).where(User.email == creds.email)):
        raise HTTPException(409, "An account with that email already exists.")
    user = User(email=creds.email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id, user.email)}


@router.post("/login")
def login(creds: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == creds.email))
    # Same error either way — don't reveal whether the email exists.
    if user is None or not verify_password(creds.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    return {"token": create_token(user.id, user.email)}
