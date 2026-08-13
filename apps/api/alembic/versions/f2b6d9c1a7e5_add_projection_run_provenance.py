"""add projection run provenance

Revision ID: f2b6d9c1a7e5
Revises: e7a1c9f4b3d2
Create Date: 2026-08-13 18:00:00.000000

Each projection-generation pass now records what produced it: model version,
generation timestamp, gameweeks covered, effective model parameters, the
team-strength values in effect at the time (frozen, so a later manual
override cannot change the explanation of a past run), and the freshest
player_snapshots row consumed. Historical projections are untouched;
run_id is nullable so pre-existing rows remain valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f2b6d9c1a7e5"
down_revision: str | None = "e7a1c9f4b3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projection_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gameweeks_covered", JSONB(), nullable=False),
        sa.Column("parameters", JSONB(), nullable=False),
        sa.Column("team_strength_snapshot", JSONB(), nullable=False),
        sa.Column("player_snapshot_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projection_runs_model_version"), "projection_runs", ["model_version"])
    op.create_index(op.f("ix_projection_runs_generated_at"), "projection_runs", ["generated_at"])

    op.add_column("projections", sa.Column("run_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_projections_run_id", "projections", "projection_runs", ["run_id"], ["id"]
    )
    op.create_index(op.f("ix_projections_run_id"), "projections", ["run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_projections_run_id"), table_name="projections")
    op.drop_constraint("fk_projections_run_id", "projections", type_="foreignkey")
    op.drop_column("projections", "run_id")

    op.drop_index(op.f("ix_projection_runs_generated_at"), table_name="projection_runs")
    op.drop_index(op.f("ix_projection_runs_model_version"), table_name="projection_runs")
    op.drop_table("projection_runs")
