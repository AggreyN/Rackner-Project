"""Bookmarks — the saved drawer.

    GET    /profile/bookmarks        -> ["notice-id", ...]   (newest first)
    PUT    /profile/bookmarks/{id}   -> 204  (idempotent save)
    DELETE /profile/bookmarks/{id}   -> 204  (idempotent unsave)

Bare opportunity ids by design (the production-handoff contract): the
frontend resolves each through GET /opportunities/{id}, which is cached.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import current_user, ensure_visible, get_db
from app.models import Bookmark, Opportunity, User

router = APIRouter(tags=["bookmarks"])


@router.get("/profile/bookmarks", response_model=list[str])
def list_bookmarks(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[str]:
    rows = db.scalars(
        select(Bookmark)
        .where(Bookmark.user_id == user.id)
        .order_by(Bookmark.created_at.desc())
    )
    return [b.opportunity_id for b in rows]


@router.put("/profile/bookmarks/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def save_bookmark(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown opportunity.")
    ensure_visible(opp, user)
    exists = db.scalar(
        select(Bookmark).where(
            Bookmark.user_id == user.id, Bookmark.opportunity_id == opportunity_id
        )
    )
    if exists is not None:
        return  # idempotent
    try:
        db.add(Bookmark(user_id=user.id, opportunity_id=opportunity_id))
        db.commit()
    except IntegrityError:
        db.rollback()  # concurrent save — same end state


@router.delete(
    "/profile/bookmarks/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_bookmark(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    db.query(Bookmark).filter(
        Bookmark.user_id == user.id, Bookmark.opportunity_id == opportunity_id
    ).delete(synchronize_session=False)
    db.commit()  # idempotent: deleting nothing is still a 204
