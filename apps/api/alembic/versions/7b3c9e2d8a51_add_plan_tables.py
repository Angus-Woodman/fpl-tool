"""add plan tables

Revision ID: 7b3c9e2d8a51
Revises: 2c7e6a1d4f3b
Create Date: 2026-08-13 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b3c9e2d8a51"
down_revision: str | None = "2c7e6a1d4f3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLAN_CHIP_ENUM = sa.Enum(
    "WILDCARD",
    "FREE_HIT",
    "BENCH_BOOST",
    "TRIPLE_CAPTAIN",
    name="planchip",
)


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_gameweek", sa.Integer(), nullable=False),
        sa.Column("end_gameweek", sa.Integer(), nullable=False),
        sa.Column("initial_bank", sa.Float(), nullable=False),
        sa.Column("initial_free_transfers", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "plan_gameweeks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("gameweek_number", sa.Integer(), nullable=False),
        sa.Column("chip", PLAN_CHIP_ENUM, nullable=True),
        sa.Column("bank", sa.Float(), nullable=False),
        sa.Column("free_transfers_available", sa.Integer(), nullable=False),
        sa.Column("transfers_made", sa.Integer(), nullable=False),
        sa.Column("points_hit", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "gameweek_number", name="uq_plan_gameweek"),
    )
    op.create_index(op.f("ix_plan_gameweeks_plan_id"), "plan_gameweeks", ["plan_id"], unique=False)
    op.create_table(
        "plan_gameweek_players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_gameweek_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("is_starting", sa.Boolean(), nullable=False),
        sa.Column("bench_order", sa.Integer(), nullable=True),
        sa.Column("is_captain", sa.Boolean(), nullable=False),
        sa.Column("is_vice_captain", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["plan_gameweek_id"], ["plan_gameweeks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_gameweek_id", "player_id", name="uq_plan_gameweek_player"),
        sa.UniqueConstraint("plan_gameweek_id", "bench_order", name="uq_plan_gameweek_bench_order"),
    )
    op.create_index(
        op.f("ix_plan_gameweek_players_plan_gameweek_id"),
        "plan_gameweek_players",
        ["plan_gameweek_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plan_gameweek_players_player_id"),
        "plan_gameweek_players",
        ["player_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_plan_gameweek_players_player_id"), table_name="plan_gameweek_players")
    op.drop_index(
        op.f("ix_plan_gameweek_players_plan_gameweek_id"),
        table_name="plan_gameweek_players",
    )
    op.drop_table("plan_gameweek_players")
    op.drop_index(op.f("ix_plan_gameweeks_plan_id"), table_name="plan_gameweeks")
    op.drop_table("plan_gameweeks")
    op.drop_table("plans")
    PLAN_CHIP_ENUM.drop(op.get_bind(), checkfirst=True)
