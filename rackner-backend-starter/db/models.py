"""Database models — the full schema for the intelligence layer.

Four tables:
    documents    one uploaded PDF
    clauses      one FAR/DFARS chunk of a document (carries page + char offsets)
    obligations  one extracted, plain-English obligation (carries its citation)
    users        only used when AUTH_ENABLED (Week 6)

Citation trail: an obligation points at its source clause, and the clause knows
its page, character range, and the pixel boxes of every word in that range — so
every claim traces back to an exact rectangle on an exact page.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    String, Text, Integer, Float, DateTime, ForeignKey, Boolean, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str | None] = mapped_column(String(1000))   # where the PDF sits on disk
    source: Mapped[str | None] = mapped_column(String(500))       # e.g. SAM.gov notice ID
    num_pages: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="processing")  # processing|ready|failed
    pii_findings: Mapped[dict | None] = mapped_column(JSON)       # what the scan saw (kinds+counts only)
    pii_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # retention (Week 4)

    clauses: Mapped[list["Clause"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    obligations: Mapped[list["Obligation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Clause(Base):
    __tablename__ = "clauses"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    clause_ref: Mapped[str | None] = mapped_column(String(50))    # "252.204-7012"
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    # Word boxes covering this clause's span: [[x0,y0,x1,y1], ...] in PDF points.
    boxes: Mapped[list | None] = mapped_column(JSON)

    document: Mapped["Document"] = relationship(back_populates="clauses")


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    source_clause_id: Mapped[int | None] = mapped_column(ForeignKey("clauses.id"))

    plain_english_text: Mapped[str] = mapped_column(Text)
    obligation_type: Mapped[str | None] = mapped_column(String(50))
    trigger_or_deadline: Mapped[str | None] = mapped_column(String(300))
    responsible_party: Mapped[str | None] = mapped_column(String(100))

    # Derived in extraction/adapter.py — never asked of the LLM.
    roles: Mapped[list | None] = mapped_column(JSON)              # ["contracts","security"] (Week 5)
    category: Mapped[str | None] = mapped_column(String(50))      # legal|reporting|security|deliverable|financial
    time_bucket: Mapped[str | None] = mapped_column(String(30))   # immediate|30_days|quarterly|ongoing|unclear

    verbatim_quote: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    # Where the quote actually sits on that page — the span-highlight payload.
    quote_char_start: Mapped[int | None] = mapped_column(Integer)
    quote_char_end: Mapped[int | None] = mapped_column(Integer)
    quote_boxes: Mapped[list | None] = mapped_column(JSON)   # [[x0,y0,x1,y1], ...]
    confidence: Mapped[float | None] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in-review|done

    document: Mapped["Document"] = relationship(back_populates="obligations")


class User(Base):
    """Only used when AUTH_ENABLED=true (Week 6). Passwords are bcrypt hashes only."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
