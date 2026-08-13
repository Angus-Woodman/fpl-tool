"""make player gameweek stats gameweek granular

Revision ID: b8d5a7c31e94
Revises: 9c41f0d6b2ae
Create Date: 2026-08-13 15:30:00.000000

The source for actuals is `/event/{id}/live/`, which aggregates per gameweek.
Fixture-level identity is dropped rather than left ambiguous; a separate table
can record fixture breakdowns if double-gameweek attribution is ever needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d5a7c31e94"
down_revision: str | None = "9c41f0d6b2ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_player_fixture_stat", "player_gameweek_stats", type_="unique")
    op.alter_column(
        "player_gameweek_stats", "fixture_id", existing_type=sa.Integer(), nullable=True
    )
    op.create_unique_constraint(
        "uq_player_gameweek_stat", "player_gameweek_stats", ["player_id", "gameweek_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_player_gameweek_stat", "player_gameweek_stats", type_="unique")
    op.execute("DELETE FROM player_gameweek_stats WHERE fixture_id IS NULL")
    op.alter_column(
        "player_gameweek_stats", "fixture_id", existing_type=sa.Integer(), nullable=False
    )
    op.create_unique_constraint(
        "uq_player_fixture_stat", "player_gameweek_stats", ["player_id", "fixture_id"]
    )
