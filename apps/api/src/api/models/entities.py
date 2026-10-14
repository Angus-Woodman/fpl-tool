import datetime as dt
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base


class PlayerPosition(str, Enum):
    GOALKEEPER = "GK"
    DEFENDER = "DEF"
    MIDFIELDER = "MID"
    FORWARD = "FWD"


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_fpl_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    short_name: Mapped[str] = mapped_column(String(10), nullable=False)
    source_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    difficulty_override: Mapped[int | None] = mapped_column(Integer)
    strength_overall_home: Mapped[int | None] = mapped_column(Integer)
    strength_overall_away: Mapped[int | None] = mapped_column(Integer)

    @property
    def effective_difficulty(self) -> int:
        return (
            self.difficulty_override
            if self.difficulty_override is not None
            else self.source_difficulty
        )


class PlayerModel(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_fpl_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    second_name: Mapped[str] = mapped_column(String(100), nullable=False)
    web_name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    position: Mapped[PlayerPosition] = mapped_column(SqlEnum(PlayerPosition), nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Upstream incoming-selectability flags; NULL means unknown (never imported or absent).
    can_select: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    can_transact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class GameweekModel(Base):
    __tablename__ = "gameweeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    deadline: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_next: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FixtureModel(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_fpl_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    gameweek_id: Mapped[int | None] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    kickoff_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    finished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PlayerGameweekStatModel(Base):
    __tablename__ = "player_gameweek_stats"
    __table_args__ = (UniqueConstraint("player_id", "gameweek_id", name="uq_player_gameweek_stat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clean_sheets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goals_conceded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class PlayerSnapshotModel(Base):
    __tablename__ = "player_snapshots"
    __table_args__ = (UniqueConstraint("player_id", "captured_at", name="uq_player_snapshot_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    captured_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    gameweek_id: Mapped[int | None] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    ownership_percent: Mapped[float] = mapped_column(Float, nullable=False)
    transfers_in: Mapped[int] = mapped_column(Integer, nullable=False)
    transfers_out: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    chance_of_playing_next_round: Mapped[int | None] = mapped_column(Integer)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    starts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    points_per_game: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    form: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    expected_goals: Mapped[float | None] = mapped_column(Float)
    expected_assists: Mapped[float | None] = mapped_column(Float)
    expected_goals_per_90: Mapped[float | None] = mapped_column(Float)
    expected_assists_per_90: Mapped[float | None] = mapped_column(Float)
    expected_goals_conceded_per_90: Mapped[float | None] = mapped_column(Float)
    goals_conceded_per_90: Mapped[float | None] = mapped_column(Float)
    clean_sheets_per_90: Mapped[float | None] = mapped_column(Float)
    saves_per_90: Mapped[float | None] = mapped_column(Float)
    starts_per_90: Mapped[float | None] = mapped_column(Float)
    defensive_contribution_per_90: Mapped[float | None] = mapped_column(Float)
    penalties_order: Mapped[int | None] = mapped_column(Integer)
    direct_freekicks_order: Mapped[int | None] = mapped_column(Integer)
    corners_order: Mapped[int | None] = mapped_column(Integer)
    team_join_date: Mapped[dt.date | None] = mapped_column(Date)
    ep_next: Mapped[float | None] = mapped_column(Float)


class ProjectionModel(Base):
    __tablename__ = "projections"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "gameweek_id",
            "generated_at",
            "model_version",
            name="uq_projection_versioned",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), index=True)
    gameweek_id: Mapped[int | None] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    projected_points: Mapped[float] = mapped_column(Float, nullable=False)
    expected_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    appearance_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    goal_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    assist_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    clean_sheet_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bonus_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    defensive_contribution_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    other_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    save_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("projection_runs.id"), index=True)


class ProjectionRunModel(Base):
    """Provenance for one projection-generation pass: what produced these rows, from what."""

    __tablename__ = "projection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    gameweeks_covered: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    # team_id (stringified) -> {source_difficulty, override, effective_difficulty}, frozen at
    # generation time so a later override change cannot alter this run's provenance.
    team_strength_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    # The captured_at of the freshest player_snapshots row consumed by this run.
    player_snapshot_generated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.UTC),
    )


class SquadModel(Base):
    __tablename__ = "squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="My Team")
    bank: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    free_transfers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=dt.datetime.now(dt.UTC),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=dt.datetime.now(dt.UTC),
    )


class SquadPlayerModel(Base):
    __tablename__ = "squad_players"
    __table_args__ = (
        UniqueConstraint("squad_id", "player_id", name="uq_squad_player"),
        UniqueConstraint("squad_id", "bench_order", name="uq_squad_bench_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("squads.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    is_starting: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bench_order: Mapped[int | None] = mapped_column(Integer)
    is_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_vice_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PlanChip(str, Enum):
    WILDCARD = "WILDCARD"
    FREE_HIT = "FREE_HIT"
    BENCH_BOOST = "BENCH_BOOST"
    TRIPLE_CAPTAIN = "TRIPLE_CAPTAIN"


class PlanModel(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="ck_plan_revision"),
        CheckConstraint(
            "foundation_state IN ('legacy_pending', 'ready')", name="ck_plan_foundation"
        ),
        CheckConstraint("starting_free_transfers BETWEEN 0 AND 5", name="ck_plan_starting_ft"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_gameweek: Mapped[int] = mapped_column(Integer, nullable=False)
    end_gameweek: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_bank: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    initial_free_transfers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    foundation_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="legacy_pending"
    )
    initialization_version: Mapped[int | None] = mapped_column(Integer)
    initialized_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    initial_bank_tenths: Mapped[int | None] = mapped_column(Integer)
    starting_free_transfers: Mapped[int | None] = mapped_column(Integer)
    boundary_origin: Mapped[str | None] = mapped_column(String(40))
    boundary_lineup: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    used_chips: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    free_hit_gameweek_19: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    bank_assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.UTC),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: dt.datetime.now(dt.UTC),
    )


class PlanGameweekModel(Base):
    __tablename__ = "plan_gameweeks"
    __table_args__ = (UniqueConstraint("plan_id", "gameweek_number", name="uq_plan_gameweek"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        index=True,
    )
    gameweek_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chip: Mapped[PlanChip | None] = mapped_column(SqlEnum(PlanChip))
    planned_chip: Mapped[str | None] = mapped_column(String(20))
    slot_lineup: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    bank: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    free_transfers_available: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    transfers_made: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points_hit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PlanGameweekPlayerModel(Base):
    __tablename__ = "plan_gameweek_players"
    __table_args__ = (
        UniqueConstraint("plan_gameweek_id", "player_id", name="uq_plan_gameweek_player"),
        UniqueConstraint("plan_gameweek_id", "bench_order", name="uq_plan_gameweek_bench_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_gameweek_id: Mapped[int] = mapped_column(
        ForeignKey("plan_gameweeks.id", ondelete="CASCADE"),
        index=True,
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    is_starting: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bench_order: Mapped[int | None] = mapped_column(Integer)
    is_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_vice_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PlanStartingPlayerModel(Base):
    __tablename__ = "plan_starting_players"
    __table_args__ = (
        UniqueConstraint("plan_id", "player_id", name="uq_plan_starting_player"),
        UniqueConstraint("plan_id", "slot_id", name="uq_plan_starting_slot"),
        UniqueConstraint("plan_id", "ownership_id", name="uq_plan_starting_ownership"),
        CheckConstraint("purchase_price_tenths > 0", name="ck_starting_purchase_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    slot_id: Mapped[UUID] = mapped_column(Uuid)
    ownership_id: Mapped[UUID] = mapped_column(Uuid)
    purchase_price_tenths: Mapped[int] = mapped_column(Integer)
    provenance: Mapped[dict[str, object]] = mapped_column(JSONB)


class PlanTransferDecisionModel(Base):
    __tablename__ = "plan_transfer_decisions"
    __table_args__ = (
        UniqueConstraint("plan_gameweek_id", "decision_id", name="uq_plan_transfer_decision"),
        UniqueConstraint(
            "plan_gameweek_id", "outgoing_player_id", name="uq_plan_transfer_outgoing"
        ),
        UniqueConstraint(
            "plan_gameweek_id", "incoming_player_id", name="uq_plan_transfer_incoming"
        ),
        UniqueConstraint(
            "plan_gameweek_id", "incoming_ownership_id", name="uq_plan_transfer_ownership"
        ),
        CheckConstraint(
            "outgoing_market_tenths > 0 AND incoming_price_tenths > 0 AND selling_price_tenths > 0",
            name="ck_transfer_prices",
        ),
        CheckConstraint("outgoing_player_id <> incoming_player_id", name="ck_transfer_players"),
        CheckConstraint(
            "outgoing_ownership_id <> incoming_ownership_id", name="ck_transfer_ownership"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_gameweek_id: Mapped[int] = mapped_column(
        ForeignKey("plan_gameweeks.id", ondelete="CASCADE"), index=True
    )
    decision_id: Mapped[UUID] = mapped_column(Uuid)
    outgoing_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    outgoing_ownership_id: Mapped[UUID] = mapped_column(Uuid)
    incoming_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    incoming_ownership_id: Mapped[UUID] = mapped_column(Uuid)
    outgoing_market_tenths: Mapped[int] = mapped_column(Integer)
    incoming_price_tenths: Mapped[int] = mapped_column(Integer)
    selling_price_tenths: Mapped[int] = mapped_column(Integer)
    observation_source: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[str] = mapped_column(String(50))
    origin: Mapped[str] = mapped_column(String(40))


class PlanMutationModel(Base):
    __tablename__ = "plan_mutations"
    __table_args__ = (
        UniqueConstraint("plan_id", "mutation_id", name="uq_plan_mutation"),
        CheckConstraint("expected_revision >= 0", name="ck_mutation_expected_revision"),
        CheckConstraint(
            "(status = 'validated_pending' AND pending_inputs IS NOT NULL "
            "AND committed_revision IS NULL) OR (status = 'committed' "
            "AND pending_inputs IS NULL AND committed_revision IS NOT NULL "
            "AND committed_revision >= 1)",
            name="ck_mutation_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    mutation_id: Mapped[UUID] = mapped_column(Uuid)
    digest: Mapped[str] = mapped_column(String(64))
    expected_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    evaluator_version: Mapped[str] = mapped_column(String(50))
    rule_fingerprint: Mapped[str] = mapped_column(String(64))
    pending_inputs: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    committed_revision: Mapped[int | None] = mapped_column(Integer)
