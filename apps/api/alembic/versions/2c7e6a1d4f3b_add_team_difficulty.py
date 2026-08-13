"""add team difficulty rating

Revision ID: 2c7e6a1d4f3b
Revises: 1db0a6b7f9c7
Create Date: 2026-08-12 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c7e6a1d4f3b"
down_revision: str | None = "1db0a6b7f9c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("teams", "difficulty")
