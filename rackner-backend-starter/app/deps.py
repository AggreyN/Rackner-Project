"""Shared FastAPI dependencies, re-exported from one place.

Routes import from here rather than reaching into app.database / app.auth, so
the wiring can change (session strategy, auth mode) without touching every
route module.
"""

from app.auth import current_user
from app.database import get_db

__all__ = ["get_db", "current_user"]


def ensure_visible(opp, user) -> None:
    """Imported opportunities are private to their uploader. 404 (not 403)
    for everyone else — revealing existence would leak business interest."""
    from fastapi import HTTPException, status

    if getattr(opp, "owner_id", None) is not None and opp.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
