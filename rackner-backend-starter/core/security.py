"""Auth & credential security (feature-flagged; AUTH_ENABLED in config).

Decisions, so nobody has to guess later:
- Passwords are NEVER stored. We store a bcrypt hash (via passlib), which is
  slow-by-design and salted per user.
- Sessions use short-lived JWTs signed with JWT_SECRET (HS256). No session
  table needed; tokens expire on their own.
- The .env file holds secrets and is git-ignored. In production (Amplify /
  AWS), secrets live in environment variables, never in code.
- All traffic must be HTTPS in production (Amplify already terminates TLS).
"""

from datetime import datetime, timedelta, timezone

import jwt  # PyJWT
from passlib.context import CryptContext

from core.config import JWT_SECRET, JWT_EXPIRY_HOURS

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
