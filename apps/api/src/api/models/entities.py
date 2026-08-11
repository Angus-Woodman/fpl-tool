import datetime as dt
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
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
    __table_args__ = (UniqueConstraint("player_id", "fixture_id", name="uq_player_fixture_stat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    gameweek_id: Mapped[int] = mapped_column(ForeignKey("gameweeks.id"), index=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False)
    goals_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clean_sheets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goals_conceded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


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
    generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)


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
