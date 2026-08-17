"""Cached AI pre-screen scores (fit_estimates).

One row per (user, opportunity): the batched card-metadata model score,
cached so estimates are stable across pages and repeat searches are free.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_fit_estimates"
down_revision = "0005_backfill_has_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fit_estimates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "opportunity_id",
            sa.String(length=255),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_fit_estimates_user_opp",
        "fit_estimates",
        ["user_id", "opportunity_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_fit_estimates_user_opp", table_name="fit_estimates")
    op.drop_table("fit_estimates")
