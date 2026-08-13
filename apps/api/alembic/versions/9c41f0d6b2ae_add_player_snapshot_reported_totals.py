"""add player snapshot reported totals

Revision ID: 9c41f0d6b2ae
Revises: 7b3c9e2d8a51
Create Date: 2026-08-13 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c41f0d6b2ae"
down_revision: str | None = "7b3c9e2d8a51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "player_snapshots",
        sa.Column("total_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_snapshots",
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_snapshots",
        sa.Column("starts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_snapshots",
        sa.Column("points_per_game", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "player_snapshots",
        sa.Column("form", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column("player_snapshots", sa.Column("expected_goals", sa.Float(), nullable=True))
    op.add_column("player_snapshots", sa.Column("expected_assists", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_snapshots", "expected_assists")
    op.drop_column("player_snapshots", "expected_goals")
    op.drop_column("player_snapshots", "form")
    op.drop_column("player_snapshots", "points_per_game")
    op.drop_column("player_snapshots", "starts")
    op.drop_column("player_snapshots", "total_points")
    op.drop_column("player_snapshots", "total_minutes")
