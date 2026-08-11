"""add squad tables

Revision ID: 5f54d7b4c21a
Revises: a4a241741f38
Create Date: 2026-08-11 01:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f54d7b4c21a"
down_revision: str | None = "a4a241741f38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "squads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("bank", sa.Float(), nullable=False),
        sa.Column("free_transfers", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "squad_players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("squad_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("is_starting", sa.Boolean(), nullable=False),
        sa.Column("bench_order", sa.Integer(), nullable=True),
        sa.Column("is_captain", sa.Boolean(), nullable=False),
        sa.Column("is_vice_captain", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["squad_id"], ["squads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("squad_id", "bench_order", name="uq_squad_bench_order"),
        sa.UniqueConstraint("squad_id", "player_id", name="uq_squad_player"),
    )
    op.create_index(
        op.f("ix_squad_players_player_id"), "squad_players", ["player_id"], unique=False
    )
    op.create_index(
        op.f("ix_squad_players_squad_id"),
        "squad_players",
        ["squad_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_squad_players_squad_id"), table_name="squad_players")
    op.drop_index(op.f("ix_squad_players_player_id"), table_name="squad_players")
    op.drop_table("squad_players")
    op.drop_table("squads")
