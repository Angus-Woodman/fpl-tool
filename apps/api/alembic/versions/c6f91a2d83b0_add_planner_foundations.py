"""Add canonical Planner inputs and minimal mutation receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c6f91a2d83b0"
down_revision: str | None = "3e8b5d1a9c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "foundation_state", sa.String(20), nullable=False, server_default="legacy_pending"
        ),
        sa.Column("initialization_version", sa.Integer()),
        sa.Column("initialized_at", sa.DateTime(timezone=True)),
        sa.Column("initial_bank_tenths", sa.Integer()),
        sa.Column("starting_free_transfers", sa.Integer()),
        sa.Column("boundary_origin", sa.String(40)),
        sa.Column("boundary_lineup", JSONB()),
        sa.Column("used_chips", JSONB(), nullable=False, server_default="[]"),
        sa.Column("free_hit_gameweek_19", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("bank_assumptions", JSONB(), nullable=False, server_default="[]"),
    ):
        op.add_column("plans", column)
    op.create_check_constraint("ck_plan_revision", "plans", "revision >= 0")
    op.create_check_constraint(
        "ck_plan_foundation", "plans", "foundation_state IN ('legacy_pending', 'ready')"
    )
    op.create_check_constraint(
        "ck_plan_starting_ft", "plans", "starting_free_transfers BETWEEN 0 AND 5"
    )
    op.add_column("plan_gameweeks", sa.Column("planned_chip", sa.String(20)))
    op.add_column("plan_gameweeks", sa.Column("slot_lineup", JSONB()))
    op.create_table(
        "plan_starting_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id", sa.Integer(), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("slot_id", sa.Uuid(), nullable=False),
        sa.Column("ownership_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_price_tenths", sa.Integer(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=False),
        sa.UniqueConstraint("plan_id", "player_id", name="uq_plan_starting_player"),
        sa.UniqueConstraint("plan_id", "slot_id", name="uq_plan_starting_slot"),
        sa.UniqueConstraint("plan_id", "ownership_id", name="uq_plan_starting_ownership"),
        sa.CheckConstraint("purchase_price_tenths > 0", name="ck_starting_purchase_price"),
    )
    op.create_index("ix_plan_starting_players_plan_id", "plan_starting_players", ["plan_id"])
    op.create_table(
        "plan_transfer_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_gameweek_id",
            sa.Integer(),
            sa.ForeignKey("plan_gameweeks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("outgoing_player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("outgoing_ownership_id", sa.Uuid(), nullable=False),
        sa.Column("incoming_player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("incoming_ownership_id", sa.Uuid(), nullable=False),
        sa.Column("outgoing_market_tenths", sa.Integer(), nullable=False),
        sa.Column("incoming_price_tenths", sa.Integer(), nullable=False),
        sa.Column("selling_price_tenths", sa.Integer(), nullable=False),
        sa.Column("observation_source", sa.String(200), nullable=False),
        sa.Column("observed_at", sa.String(50), nullable=False),
        sa.Column("origin", sa.String(40), nullable=False),
        sa.UniqueConstraint("plan_gameweek_id", "decision_id", name="uq_plan_transfer_decision"),
        sa.UniqueConstraint(
            "plan_gameweek_id", "outgoing_player_id", name="uq_plan_transfer_outgoing"
        ),
        sa.UniqueConstraint(
            "plan_gameweek_id", "incoming_player_id", name="uq_plan_transfer_incoming"
        ),
        sa.UniqueConstraint(
            "plan_gameweek_id", "incoming_ownership_id", name="uq_plan_transfer_ownership"
        ),
        sa.CheckConstraint(
            "outgoing_market_tenths > 0 AND incoming_price_tenths > 0 AND selling_price_tenths > 0",
            name="ck_transfer_prices",
        ),
        sa.CheckConstraint("outgoing_player_id <> incoming_player_id", name="ck_transfer_players"),
        sa.CheckConstraint(
            "outgoing_ownership_id <> incoming_ownership_id", name="ck_transfer_ownership"
        ),
    )
    op.create_index(
        "ix_plan_transfer_decisions_plan_gameweek_id",
        "plan_transfer_decisions",
        ["plan_gameweek_id"],
    )
    op.create_table(
        "plan_mutations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id", sa.Integer(), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("mutation_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evaluator_version", sa.String(50), nullable=False),
        sa.Column("rule_fingerprint", sa.String(64), nullable=False),
        sa.Column("pending_inputs", JSONB(none_as_null=True)),
        sa.Column("committed_revision", sa.Integer()),
        sa.UniqueConstraint("plan_id", "mutation_id", name="uq_plan_mutation"),
        sa.CheckConstraint("expected_revision >= 0", name="ck_mutation_expected_revision"),
        sa.CheckConstraint(
            "(status = 'validated_pending' AND pending_inputs IS NOT NULL "
            "AND committed_revision IS NULL) OR (status = 'committed' "
            "AND pending_inputs IS NULL AND committed_revision IS NOT NULL "
            "AND committed_revision >= 1)",
            name="ck_mutation_status",
        ),
    )
    op.create_index("ix_plan_mutations_plan_id", "plan_mutations", ["plan_id"])


def downgrade() -> None:
    new_writes = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM plans WHERE revision > 0 "
                "OR (foundation_state = 'ready' "
                "AND boundary_origin <> 'legacy_first_gameweek_assumed'))"
            )
        )
        .scalar_one()
    )
    if new_writes:
        raise RuntimeError(
            "Planner has new-only writes. Back up/export and explicitly convert or restore "
            "before downgrade; an in-place downgrade would lose data."
        )
    for table in ("plan_mutations", "plan_transfer_decisions", "plan_starting_players"):
        op.drop_table(table)
    op.drop_column("plan_gameweeks", "slot_lineup")
    op.drop_column("plan_gameweeks", "planned_chip")
    for constraint in ("ck_plan_starting_ft", "ck_plan_foundation", "ck_plan_revision"):
        op.drop_constraint(constraint, "plans", type_="check")
    for column in (
        "bank_assumptions",
        "free_hit_gameweek_19",
        "used_chips",
        "boundary_lineup",
        "boundary_origin",
        "starting_free_transfers",
        "initial_bank_tenths",
        "initialized_at",
        "initialization_version",
        "foundation_state",
        "revision",
    ):
        op.drop_column("plans", column)
