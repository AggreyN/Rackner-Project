"""Contact email-verification bookkeeping (feature-flagged, Tier 2 only).

Three nullable columns on contacts: the normalized verification status, the
provider that produced it, and when it was checked (drives the re-verify TTL).
Null everywhere until EMAIL_VERIFY_PROVIDER is switched on, so this migration
changes nothing about a default deployment.

Revision ID: 0010_contact_verification
Revises: 0009_user_content
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_contact_verification"
down_revision = "0009_user_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts", sa.Column("verification_status", sa.String(20), nullable=True)
    )
    op.add_column(
        "contacts", sa.Column("verification_provider", sa.String(20), nullable=True)
    )
    op.add_column(
        "contacts",
        sa.Column("verification_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "verification_checked_at")
    op.drop_column("contacts", "verification_provider")
    op.drop_column("contacts", "verification_status")
