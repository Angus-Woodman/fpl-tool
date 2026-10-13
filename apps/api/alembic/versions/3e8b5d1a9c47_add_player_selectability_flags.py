"""add player selectability flags

Revision ID: 3e8b5d1a9c47
Revises: a1c8f3e6d940
Create Date: 2026-10-13 12:00:00.000000

Retains FPL's upstream `can_select` / `can_transact` incoming-selectability
flags. Additive and nullable with no default and no backfill: existing rows
read as unknown (NULL) until the next bootstrap-static refresh populates them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e8b5d1a9c47"
down_revision: str | None = "a1c8f3e6d940"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("players", sa.Column("can_select", sa.Boolean(), nullable=True))
    op.add_column("players", sa.Column("can_transact", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "can_transact")
    op.drop_column("players", "can_select")
