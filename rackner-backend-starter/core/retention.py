"""3-day document retention (security requirement).

Every uploaded contract gets an expires_at stamp (upload time + RETENTION_DAYS).
purge_expired() hard-deletes the PDF from disk AND all database rows.
It runs (a) on app startup, (b) hourly in the background, and (c) lazily
whenever a document is fetched — so expiry holds even if the server slept.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import RETENTION_DAYS
from db.models import Document


def expiry_from_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)


def is_expired(doc: Document) -> bool:
    exp = doc.expires_at
    if exp is None:
        return False
    if exp.tzinfo is None:  # tolerate naive timestamps from older rows
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= datetime.now(timezone.utc)


def _delete_document(session: Session, doc: Document) -> None:
    # Remove the file from disk first, then the rows (cascade handles children).
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass  # file already gone — DB cleanup still proceeds
    session.delete(doc)


def purge_expired(session: Session) -> int:
    """Delete every expired document. Returns how many were removed."""
    removed = 0
    for doc in session.scalars(select(Document)):
        if is_expired(doc):
            _delete_document(session, doc)
            removed += 1
    session.commit()
    return removed
