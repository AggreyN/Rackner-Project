"""One analysis per (opportunity, user), enforced by the database.

The generation stampede (since fixed at the route layer) could persist
duplicate analysis rows for the same opportunity+user. Reads already pick the
newest, so the KEPT row on dedupe is the newest (MAX id); older duplicates
are dropped. The unique index turns any future double-persist into an
IntegrityError the route handles by serving the winner.
"""

import sqlalchemy as sa  # noqa: F401  (parity with sibling migrations)
from alembic import op

revision = "0004_analyses_unique"
down_revision = "0003_full_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM analyses WHERE id NOT IN "
        "(SELECT MAX(id) FROM analyses GROUP BY opportunity_id, user_id)"
    )
    op.create_index(
        "uq_analyses_opportunity_user",
        "analyses",
        ["opportunity_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_analyses_opportunity_user", table_name="analyses")
