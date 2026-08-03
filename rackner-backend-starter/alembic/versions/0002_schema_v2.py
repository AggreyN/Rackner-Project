"""Conform the schema to SCHEMA_v2 (Remy's types.ts contract).

Three groups of change:
  1. opportunities — recompete radar. `kind` splits SAM.gov notices from
     USAspending expiring awards; expiry_date/current_award_value carry the
     recompete signal. response_deadline/estimated_value are replaced by
     close_date/est_value (est_value becomes a display STRING per types.ts).
  2. analyses — v2 keeps BOTH `band` (enum) and `verdict` (free prose), so the
     old `verdict` enum column becomes `band` and the old `summary` prose column
     becomes `verdict`. Renames, not drops, so existing rows survive.
  3. source_documents / source_sections — new. The grounding record behind
     `GET /document`, persisted so the analysis path and the document endpoint
     serve byte-identical section text.

Revision ID: 0002_schema_v2
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_schema_v2"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. opportunities: recompete radar + v2 field names -------------------
    op.add_column("opportunities", sa.Column("office", sa.String(length=500), nullable=True))
    op.add_column(
        "opportunities", sa.Column("solicitation_number", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "opportunities",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="solicitation"),
    )
    op.add_column("opportunities", sa.Column("close_date", sa.Date(), nullable=True))
    op.add_column("opportunities", sa.Column("est_value", sa.String(length=255), nullable=True))
    op.add_column("opportunities", sa.Column("incumbent", sa.String(length=500), nullable=True))
    op.add_column("opportunities", sa.Column("expiry_date", sa.Date(), nullable=True))
    op.add_column("opportunities", sa.Column("current_award_value", sa.Numeric(), nullable=True))
    op.create_index("ix_opportunities_expiry_date", "opportunities", ["expiry_date"])

    # Carry v1 data across before dropping the old columns.
    op.execute("UPDATE opportunities SET close_date = response_deadline")
    op.execute(
        "UPDATE opportunities SET est_value = CAST(estimated_value AS VARCHAR) "
        "WHERE estimated_value IS NOT NULL"
    )
    op.drop_column("opportunities", "response_deadline")
    op.drop_column("opportunities", "estimated_value")

    # --- 2. analyses: score, and band/verdict as two distinct things ----------
    op.alter_column("analyses", "compatibility_score", new_column_name="score")
    # Old `verdict` held the enum -> that is v2's `band`.
    op.alter_column("analyses", "verdict", new_column_name="band")
    # Old `summary` held prose -> that is v2's `verdict`. Already Text, so this
    # is a pure rename (no ALTER TYPE, which SQLite can't do).
    op.alter_column("analyses", "summary", new_column_name="verdict")

    # --- 3. contacts: v2 names ------------------------------------------------
    op.alter_column("contacts", "agency", new_column_name="office")
    op.alter_column(
        "contacts", "procurement_integrity_flag", new_column_name="active_solicitation"
    )

    # --- 4. lifecycle_profiles: upload provenance -----------------------------
    op.add_column(
        "lifecycle_profiles",
        sa.Column("filename", sa.String(length=512), nullable=False, server_default=""),
    )

    # --- 5. the grounding record ---------------------------------------------
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opportunity_id", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_source_documents_opportunity_id", "source_documents", ["opportunity_id"]
    )

    op.create_table(
        "source_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("heading", sa.String(length=1000), nullable=False, server_default=""),
        # The canonical string. Never normalized on the way in or out.
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_source_sections_document_id", "source_sections", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_source_sections_document_id", table_name="source_sections")
    op.drop_table("source_sections")
    op.drop_index("ix_source_documents_opportunity_id", table_name="source_documents")
    op.drop_table("source_documents")

    op.drop_column("lifecycle_profiles", "filename")

    op.alter_column(
        "contacts", "active_solicitation", new_column_name="procurement_integrity_flag"
    )
    op.alter_column("contacts", "office", new_column_name="agency")

    op.alter_column("analyses", "verdict", new_column_name="summary")
    op.alter_column("analyses", "band", new_column_name="verdict")
    op.alter_column("analyses", "score", new_column_name="compatibility_score")

    op.add_column("opportunities", sa.Column("estimated_value", sa.Numeric(), nullable=True))
    op.add_column("opportunities", sa.Column("response_deadline", sa.Date(), nullable=True))
    op.execute("UPDATE opportunities SET response_deadline = close_date")
    op.drop_index("ix_opportunities_expiry_date", table_name="opportunities")
    for col in (
        "current_award_value",
        "expiry_date",
        "incumbent",
        "est_value",
        "close_date",
        "kind",
        "solicitation_number",
        "office",
    ):
        op.drop_column("opportunities", col)
