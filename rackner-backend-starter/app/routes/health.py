"""Health + a protected sample route (`/me`) that exercises current_user."""

from fastapi import APIRouter, Depends

from app import config
from app.auth import current_user
from app.models import User

router = APIRouter(tags=["health"])


@router.get("/")
def health() -> dict:
    """Liveness check — no auth required."""
    return {
        "status": "ok",
        "service": "rackner-fdi-backend",
        "auth_mode": config.AUTH_MODE,
    }


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    """Protected: returns the authenticated user. 401 without a valid token."""
    return {
        "id": user.id,
        "email": user.email,
        "cognito_sub": user.cognito_sub,
        "auth_mode": config.AUTH_MODE,
    }
