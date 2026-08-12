"""Repair 0003's backfill: pre-existing documents DID include descriptions.

0003 added has_description with server_default false. But every document
built before 0003 was built FROM the description (attachments didn't exist
yet), so false is wrong for all of them — and it makes the first
generation-path read of each old document trigger a pointless rebuild:
identical text, a new row, and the opportunity's cached analyses deleted
for nothing. Measured in prod 2026-08-12: the rebuild also re-downloads
attachments (SAM quota) for linked notices.

The repair marks a document as description-built when it has sections and
its opportunity currently has a description. For pre-0003 rows that is
exact (sections could only have come from the description). The one
imprecise case — a post-0003 attachments-only document whose description
arrived after its build but before this migration runs — would wrongly
skip its description rebuild; the window is hours on one deployment and
the attachment-growth path still rebuilds those documents.
"""

import sqlalchemy as sa  # noqa: F401  (parity with sibling migrations)
from alembic import op

revision = "0005_backfill_has_description"
down_revision = "0004_analyses_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE source_documents
        SET has_description = TRUE
        WHERE id IN (
            SELECT d.id
            FROM source_documents AS d
            JOIN opportunities AS o ON o.id = d.opportunity_id
            WHERE o.description IS NOT NULL
              AND o.description != ''
              AND EXISTS (
                  SELECT 1 FROM source_sections s WHERE s.document_id = d.id
              )
        )
        """
    )


def downgrade() -> None:
    # The 0003 state this repairs was itself a backfill default; restoring
    # false for every row is the faithful inverse.
    op.execute("UPDATE source_documents SET has_description = FALSE")
