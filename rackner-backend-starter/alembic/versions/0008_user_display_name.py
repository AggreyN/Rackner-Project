"""users.display_name — 'Welcome, {username}'.

Mirrors the Cognito `name` attribute (synced from ID-token claims per
request). Nullable: the UI falls back to the email local-part.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_user_display_name"
down_revision = "0007_search_fetch_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
