"""separate imported team strength from manual override

Revision ID: c3f6b81d47a2
Revises: b8d5a7c31e94
Create Date: 2026-08-13 16:00:00.000000

The single `difficulty` column conflated FPL's imported rating with the user's
manual judgement, so an import could silently overwrite an override and an
override could never be removed to reveal the underlying value.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f6b81d47a2"
down_revision: str | None = "b8d5a7c31e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teams", sa.Column("source_difficulty", sa.Integer(), nullable=False, server_default="3")
    )
    op.add_column("teams", sa.Column("difficulty_override", sa.Integer(), nullable=True))
    op.add_column("teams", sa.Column("strength_overall_home", sa.Integer(), nullable=True))
    op.add_column("teams", sa.Column("strength_overall_away", sa.Integer(), nullable=True))
    op.execute("UPDATE teams SET source_difficulty = difficulty")
    op.drop_column("teams", "difficulty")


def downgrade() -> None:
    op.add_column(
        "teams", sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3")
    )
    op.execute("UPDATE teams SET difficulty = COALESCE(difficulty_override, source_difficulty)")
    op.drop_column("teams", "strength_overall_away")
    op.drop_column("teams", "strength_overall_home")
    op.drop_column("teams", "difficulty_override")
    op.drop_column("teams", "source_difficulty")
