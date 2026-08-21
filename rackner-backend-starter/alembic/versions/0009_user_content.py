"""User content: bookmarks, imported opportunities, description-fetch stamp.

- bookmarks: per-user saved opportunities (unique per pair).
- opportunities.owner_id: imported documents are private to their uploader
  (null = public/SAM-sourced). import_hash dedupes re-uploads per owner.
- opportunities.description_fetched_at: repairs an audit-2 regression — the
  detail view's skip-refetch guard keyed off fetched_at, which search stamps,
  so freshly searched rows NEVER got their description fetched. This stamp
  records actual description attempts instead.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_user_content"
down_revision = "0008_user_display_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch mode: SQLite cannot ALTER-in a foreign-keyed column; batch
    # recreates the table there and degrades to plain ALTERs on Postgres.
    with op.batch_alter_table("opportunities") as batch:
        batch.add_column(
            sa.Column("description_fetched_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("import_hash", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_opportunities_owner_id_users", "users", ["owner_id"], ["id"],
            ondelete="CASCADE",
        )
    op.create_index("ix_opportunities_owner_id", "opportunities", ["owner_id"])
    op.create_table(
        "bookmarks",
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_bookmarks_user_opp", "bookmarks", ["user_id", "opportunity_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_bookmarks_user_opp", table_name="bookmarks")
    op.drop_table("bookmarks")
    op.drop_index("ix_opportunities_owner_id", table_name="opportunities")
    with op.batch_alter_table("opportunities") as batch:
        batch.drop_constraint("fk_opportunities_owner_id_users", type_="foreignkey")
        batch.drop_column("import_hash")
        batch.drop_column("owner_id")
        batch.drop_column("description_fetched_at")
