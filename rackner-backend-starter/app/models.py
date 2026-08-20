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
    Index,
    Integer,
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
    # Display name ("Welcome, {username}"). In Cognito mode this mirrors the
    # pool's `name` attribute (synced from ID-token claims on every request);
    # set it with scripts/set_cognito_username.sh. Null falls back to the
    # email local-part in the UI.
    display_name: Mapped[str | None] = mapped_column(String(255))
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
    set_aside_status: Mapped[list | None] = mapped_column(JSON)  # → wire `set_asides`
    # Kept on disk but NOT on the v2 wire type: they still feed past_performance
    # and pricing_size_fit scoring server-side. See SCHEMA_v2.md "DB ↔ wire".
    past_performance: Mapped[list | None] = mapped_column(JSON)
    contract_vehicles: Mapped[list | None] = mapped_column(JSON)
    size_min: Mapped[float | None] = mapped_column(Numeric)
    size_max: Mapped[float | None] = mapped_column(Numeric)
    # Provenance of the uploaded plan (v2 exposes filename + uploaded_at).
    filename: Mapped[str] = mapped_column(String(512), default="")
    source_s3_key: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped["User"] = relationship(back_populates="lifecycle_profiles")


class Opportunity(Base):
    """A capture target. Either a SAM.gov notice or — when kind='expiring_award' —
    a USAspending award whose period of performance is ending (a recompete that
    hasn't been solicited yet). The PK is SAM.gov's notice id or the award id."""

    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    title: Mapped[str] = mapped_column(String(1000))
    agency: Mapped[str] = mapped_column(String(500))
    office: Mapped[str | None] = mapped_column(String(500))
    solicitation_number: Mapped[str | None] = mapped_column(String(255))
    naics: Mapped[str | None] = mapped_column(String(20))
    set_aside: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="solicitation")
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    # Live solicitations. `days_to_close` is derived at serialization, not stored.
    close_date: Mapped[date | None] = mapped_column(Date)
    est_value: Mapped[str | None] = mapped_column(String(255))  # display string
    incumbent: Mapped[str | None] = mapped_column(String(500))
    # Recompete radar — expiring_award rows only; null on live solicitations.
    # `months_to_expiry` is derived from expiry_date at serialization.
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    current_award_value: Mapped[float | None] = mapped_column(Numeric)
    # SAM.gov attachment download URLs (resourceLinks) — the full solicitation
    # package lives behind these, not in the description. Captured at search
    # time so fetching them later costs no extra notice lookup.
    resource_links: Mapped[list | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    source_documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class SearchFetch(Base):
    """Freshness ledger: when was this (query, kinds) last fetched LIVE.

    Within SAM_SEARCH_TTL_HOURS the search serves cached opportunity rows and
    spends ZERO SAM quota — repeat searches and dashboard loads are free. A
    stale or unseen query spends exactly one live call and refreshes the
    ledger. This is what makes a 10-call/day key livable.
    """

    __tablename__ = "search_fetches"
    __table_args__ = (
        Index("uq_search_fetches_query_key", "query_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    query_key: Mapped[str] = mapped_column(String(64))  # sha256 hex
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FitEstimate(Base):
    """Cached AI pre-screen score for one (user, opportunity) card.

    Search pages are scored in ONE batched model call from card metadata; the
    result is cached here so the number is STABLE across search → detail →
    tomorrow, and repeat searches cost nothing. Invalidated when the user
    uploads a new lifecycle plan (an estimate against an old profile is
    meaningless). At serialization time a cached ANALYSIS score always takes
    precedence over any estimate — once the researched number exists, the
    card must agree with the analysis screen.
    """

    __tablename__ = "fit_estimates"
    __table_args__ = (
        Index("uq_fit_estimates_user_opp", "user_id", "opportunity_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float)  # 0–100
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class Analysis(Base):
    """Kaliza's LLM output for one opportunity + user. factors/obligations are JSON."""

    __tablename__ = "analyses"
    # Parity with migration 0004 — the IntegrityError-serve-the-winner path
    # in routes/analysis.py depends on this existing wherever the schema
    # came from (alembic or metadata.create_all).
    __table_args__ = (
        Index(
            "uq_analyses_opportunity_user",
            "opportunity_id",
            "user_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float)  # 0–100
    band: Mapped[str] = mapped_column(String(20))  # pursue | conditional | no_bid
    # Free-text one-liner for humans. v2 keeps `band` AND `verdict` as separate
    # things — `verdict` is prose, `band` is the enum. Not a rename.
    verdict: Mapped[str] = mapped_column(Text, default="")
    factors: Mapped[list | None] = mapped_column(JSON)  # [FitFactor]
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
    title: Mapped[str] = mapped_column(String(255), default="")
    office: Mapped[str] = mapped_column(String(500), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Procurement Integrity Act guard: true while the solicitation is active.
    active_solicitation: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    opportunity: Mapped["Opportunity"] = relationship(back_populates="contacts")


class SourceDocument(Base):
    """The parsed solicitation behind one opportunity — the grounding record.

    Persisted so `GET /document` and the analysis path read the byte-identical
    section text. That identity is what makes the UI's `text.indexOf(quote)`
    highlight succeed for every verified quote.
    """

    __tablename__ = "source_documents"
    # Parity with migration 0003 — one grounding document per opportunity,
    # relied on by the losing-builder-serves-the-winner path in
    # routes/documents.py.
    __table_args__ = (
        Index(
            "uq_source_documents_opportunity_id",
            "opportunity_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(1000), default="")
    # Build bookkeeping. `attachments_ingested` = blobs in THIS build (drives
    # the grew-so-invalidate decision). `attachments_accounted` = links
    # RESOLVED — fetched or permanently unfetchable (404, unsupported format);
    # a quota-stopped pass leaves it low so a later request retries, while a
    # completed pass raises it to len(links) so dead links are never
    # re-attempted on every read. `has_description` records whether the build
    # included the notice description, which can arrive AFTER the first build.
    # Any rebuild of a non-empty document deletes dependent analyses, so
    # stored citations can never point at text that changed underneath.
    attachments_ingested: Mapped[int] = mapped_column(Integer, default=0)
    attachments_accounted: Mapped[int] = mapped_column(Integer, default=0)
    has_description: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    opportunity: Mapped["Opportunity"] = relationship(
        back_populates="source_documents"
    )
    sections: Mapped[list["SourceSection"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="SourceSection.position",
    )


class SourceSection(Base):
    """One clause/section of a parsed solicitation.

    `text` is the canonical string. Never normalize it on the way in or out —
    quote verification and the UI highlight both depend on it being byte-exact.
    """

    __tablename__ = "source_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    ref: Mapped[str] = mapped_column(String(255), default="")  # "C.3.1", no "§"
    heading: Mapped[str] = mapped_column(String(1000), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0)  # document order

    document: Mapped["SourceDocument"] = relationship(back_populates="sections")
