"""add pre-season player snapshot signals

Revision ID: d47e2a95c6b0
Revises: c3f6b81d47a2
Create Date: 2026-08-13 16:15:00.000000

Per-90 rates, set-piece order and join date are overwritten in place once the
season starts, so they are captured before GW1. `ep_next` is FPL's own forecast,
retained as an external benchmark and never used as a model feature.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d47e2a95c6b0"
down_revision: str | None = "c3f6b81d47a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FLOAT_COLUMNS = (
    "expected_goals_per_90",
    "expected_assists_per_90",
    "expected_goals_conceded_per_90",
    "goals_conceded_per_90",
    "clean_sheets_per_90",
    "saves_per_90",
    "starts_per_90",
    "defensive_contribution_per_90",
    "ep_next",
)

INTEGER_COLUMNS = (
    "penalties_order",
    "direct_freekicks_order",
    "corners_order",
)


def upgrade() -> None:
    for name in FLOAT_COLUMNS:
        op.add_column("player_snapshots", sa.Column(name, sa.Float(), nullable=True))
    for name in INTEGER_COLUMNS:
        op.add_column("player_snapshots", sa.Column(name, sa.Integer(), nullable=True))
    op.add_column("player_snapshots", sa.Column("team_join_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_snapshots", "team_join_date")
    for name in reversed(INTEGER_COLUMNS):
        op.drop_column("player_snapshots", name)
    for name in reversed(FLOAT_COLUMNS):
        op.drop_column("player_snapshots", name)
