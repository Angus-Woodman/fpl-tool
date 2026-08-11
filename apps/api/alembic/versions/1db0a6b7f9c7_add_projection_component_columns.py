"""add projection component columns

Revision ID: 1db0a6b7f9c7
Revises: 5f54d7b4c21a
Create Date: 2026-08-11 09:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1db0a6b7f9c7"
down_revision: str | None = "5f54d7b4c21a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projections",
        sa.Column("appearance_points", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "projections",
        sa.Column("goal_points", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "projections",
        sa.Column("assist_points", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "projections",
        sa.Column("clean_sheet_points", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "projections",
        sa.Column("bonus_points", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "projections",
        sa.Column(
            "defensive_contribution_points",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "projections",
        sa.Column("other_points", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("projections", "other_points")
    op.drop_column("projections", "defensive_contribution_points")
    op.drop_column("projections", "bonus_points")
    op.drop_column("projections", "clean_sheet_points")
    op.drop_column("projections", "assist_points")
    op.drop_column("projections", "goal_points")
    op.drop_column("projections", "appearance_points")
