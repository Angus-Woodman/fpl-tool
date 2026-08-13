"""add projection save_points column

Revision ID: a1c8f3e6d940
Revises: f2b6d9c1a7e5
Create Date: 2026-08-13 19:00:00.000000

component_v3 is the first model version to project goalkeeper save points;
the existing component columns had no honest place to store them. Additive
and backward compatible: baseline_v1/baseline_v2 rows default to 0.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c8f3e6d940"
down_revision: str | None = "f2b6d9c1a7e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projections",
        sa.Column("save_points", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("projections", "save_points")
