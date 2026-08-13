"""add started flag to player gameweek stats

Revision ID: e7a1c9f4b3d2
Revises: d47e2a95c6b0
Create Date: 2026-08-13 17:00:00.000000

/event/{id}/live/ reports `starts` per gameweek, distinguishing a start from a
substitute appearance -- the observation the in-season expected-minutes model
needs. Not time-sensitive: past gameweeks remain queryable and the existing
import is idempotent, so this backfills cleanly whenever it is added.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1c9f4b3d2"
down_revision: str | None = "d47e2a95c6b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "player_gameweek_stats",
        sa.Column("started", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("player_gameweek_stats", "started")
