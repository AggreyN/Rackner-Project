"""
Database tables, defined as Python classes (SQLAlchemy ORM).

>>> This is your WEEK 4 deliverable. <<<
It's included now as a STARTING POINT so you can see where things are headed.
You'll refine these columns together with Role 1 once the obligation JSON
schema is locked. Don't over-build it in Week 1 — just read it to orient.

Each class below becomes a table in Postgres.
"""

from datetime import datetime

from sqlalchemy import (
    String, Text, Integer, Float, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class Document(Base):
    """One uploaded contract / solicitation PDF."""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    source: Mapped[str | None] = mapped_column(String(500))      # e.g. SAM.gov notice ID
    num_pages: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clauses: Mapped[list["Clause"]] = relationship(back_populates="document")
    obligations: Mapped[list["Obligation"]] = relationship(back_populates="document")


class Clause(Base):
    """A single FAR/DFARS clause or section chunk (output of your Week 3 segmentation)."""
    __tablename__ = "clauses"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    clause_ref: Mapped[str | None] = mapped_column(String(50))    # e.g. "252.204-7012"
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)       # for citation highlighting
    char_end: Mapped[int | None] = mapped_column(Integer)

    document: Mapped["Document"] = relationship(back_populates="clauses")


class Obligation(Base):
    """A single 'thing you must do', extracted by the LLM (Role 1) — the heart of the product."""
    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    source_clause_id: Mapped[int | None] = mapped_column(ForeignKey("clauses.id"))

    plain_english_text: Mapped[str] = mapped_column(Text)         # "Report cyber incidents within 72 hours"
    obligation_type: Mapped[str | None] = mapped_column(String(50))   # report / deliverable / cyber / insurance / flow-down
    trigger_or_deadline: Mapped[str | None] = mapped_column(String(300))
    responsible_party: Mapped[str | None] = mapped_column(String(100))

    verbatim_quote: Mapped[str | None] = mapped_column(Text)      # exact source text (Week 7 verification)
    page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)   # quote found in source? (Week 7)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open / in-review / done (Week 6)

    document: Mapped["Document"] = relationship(back_populates="obligations")


# WEEK 6 / WEEK 9: you'll add `Deadline`, `Review`, and eval-set tables here.
