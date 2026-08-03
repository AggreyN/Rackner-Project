"""Database models — the 5 tables behind Rackner FDI.

Field names mirror SCHEMA.md (the shared contract). JSON columns hold the
nested shapes defined there (factors, obligations, the lifecycle lists) so the
API can return them verbatim without a mapping layer.

Note on one intentional DB↔wire difference: SCHEMA.md exposes lifecycle sizing
as `size_targets: {min_value, max_value}`. On disk we store two plain numeric
columns, `size_min` / `size_max`; the API assembles them back into
`size_targets` when it serializes a LifecycleProfile.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Set in Cognito mode (Cognito owns the identity); null in local mode.
    cognito_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Set in local demo mode only (bcrypt hash); null in Cognito mode.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    lifecycle_profiles: Mapped[list["LifecycleProfile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class LifecycleProfile(Base):
    """Parsed from the user's uploaded Opportunity Lifecycle plan. Drives scoring."""

    __tablename__ = "lifecycle_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    capabilities: Mapped[list | None] = mapped_column(JSON)
    target_agencies: Mapped[list | None] = mapped_column(JSON)
    naics_codes: Mapped[list | None] = mapped_column(JSON)
    past_performance: Mapped[list | None] = mapped_column(JSON)
    contract_vehicles: Mapped[list | None] = mapped_column(JSON)
    set_aside_status: Mapped[list | None] = mapped_column(JSON)
    size_min: Mapped[float | None] = mapped_column(Numeric)  # → size_targets.min_value
    size_max: Mapped[float | None] = mapped_column(Numeric)  # → size_targets.max_value
    source_s3_key: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="lifecycle_profiles")


class Opportunity(Base):
    """A SAM.gov solicitation. Cached here; the PK is SAM.gov's notice id."""

    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # SAM.gov notice id
    title: Mapped[str] = mapped_column(String(1000))
    agency: Mapped[str] = mapped_column(String(500))
    naics: Mapped[str | None] = mapped_column(String(20))
    set_aside: Mapped[str | None] = mapped_column(String(255))
    response_deadline: Mapped[date | None] = mapped_column(Date)
    estimated_value: Mapped[float | None] = mapped_column(Numeric)
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class Analysis(Base):
    """Kaliza's LLM output for one opportunity + user. factors/obligations are JSON."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    compatibility_score: Mapped[float] = mapped_column(Float)  # 0–100
    verdict: Mapped[str] = mapped_column(String(20))  # pursue | conditional | no_bid
    summary: Mapped[str] = mapped_column(Text, default="")
    factors: Mapped[list | None] = mapped_column(JSON)  # [{name,weight,score,rationale}]
    obligations: Mapped[list | None] = mapped_column(JSON)  # [Obligation]
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="analyses")
    user: Mapped["User"] = relationship(back_populates="analyses")


class Contact(Base):
    """A contracting contact discovered for an opportunity. Human-in-the-loop."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    agency: Mapped[str] = mapped_column(String(500))
    email: Mapped[str] = mapped_column(String(320))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    procurement_integrity_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="contacts")
