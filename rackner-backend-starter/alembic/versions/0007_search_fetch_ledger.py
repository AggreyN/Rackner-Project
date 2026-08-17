"""Freshness ledger for SAM.gov searches.

One row per normalized (query, kinds): when it was last fetched LIVE. Within
the freshness window the search serves cached rows and spends zero SAM quota;
after it, one live call refreshes both the rows and the ledger.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_search_fetch_ledger"
down_revision = "0006_fit_estimates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_fetches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query_key", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_search_fetches_query_key", "search_fetches", ["query_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_search_fetches_query_key", table_name="search_fetches")
    op.drop_table("search_fetches")
