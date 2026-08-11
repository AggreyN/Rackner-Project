"""Full-document ingestion: SAM attachment links + build bookkeeping.

opportunities.resource_links          — SAM resourceLinks (attachment download
                                        URLs) captured at search time.
source_documents.attachments_ingested — blobs in the current build (drives the
                                        grew-so-invalidate-analyses decision).
source_documents.attachments_accounted— links resolved (fetched or permanently
                                        unfetchable); stops dead links being
                                        re-downloaded on every read.
source_documents.has_description      — whether the build included the notice
                                        description (it can arrive after the
                                        first build).
Unique index on source_documents.opportunity_id — one grounding document per
opportunity, enforced by the database rather than by convention; concurrent
builders (detail-view prewarm vs a document GET) lose the race cleanly instead
of inserting a second document. Existing duplicates are removed first, keeping
the oldest row (the one whose text stored citations were verified against).

Column additions are nullable/defaulted — SQLite-safe (no ALTER TYPE).
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_full_documents"
down_revision = "0002_schema_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("resource_links", sa.JSON(), nullable=True))
    for name in ("attachments_ingested", "attachments_accounted"):
        op.add_column(
            "source_documents",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
        )
    op.add_column(
        "source_documents",
        sa.Column(
            "has_description", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute(
        "DELETE FROM source_documents WHERE id NOT IN "
        "(SELECT MIN(id) FROM source_documents GROUP BY opportunity_id)"
    )
    op.create_index(
        "uq_source_documents_opportunity_id",
        "source_documents",
        ["opportunity_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_source_documents_opportunity_id", table_name="source_documents")
    op.drop_column("source_documents", "has_description")
    op.drop_column("source_documents", "attachments_accounted")
    op.drop_column("source_documents", "attachments_ingested")
    op.drop_column("opportunities", "resource_links")
