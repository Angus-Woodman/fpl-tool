from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class PlayerPosition(StrEnum):
    GOALKEEPER = "GK"
    DEFENDER = "DEF"
    MIDFIELDER = "MID"
    FORWARD = "FWD"


@dataclass(frozen=True)
class Team:
    id: int
    name: str
    short_name: str
    external_fpl_id: int
    difficulty: int


@dataclass(frozen=True)
class Player:
    id: int
    external_fpl_id: int
    first_name: str
    second_name: str
    web_name: str
    team_id: int
    position: PlayerPosition
    current_price: float
    status: str


@dataclass(frozen=True)
class Gameweek:
    id: int
    number: int
    name: str
    deadline: dt.datetime
    is_current: bool
    is_next: bool
    is_finished: bool


@dataclass(frozen=True)
class Fixture:
    id: int
    external_fpl_id: int
    gameweek_id: int | None
    home_team_id: int
    away_team_id: int
    kickoff_time: dt.datetime
    home_score: int | None
    away_score: int | None
    finished: bool


@dataclass(frozen=True)
class PlayerGameweekStat:
    player_id: int
    gameweek_id: int
    fixture_id: int
    minutes: int
    total_points: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    bonus: int
    bps: int


@dataclass(frozen=True)
class PlayerSnapshot:
    """Mutable player state as reported at `captured_at`.

    The reported totals describe the previous season until the new one begins.
    """

    player_id: int
    captured_at: dt.datetime
    gameweek_id: int | None
    price: float
    ownership_percent: float
    transfers_in: int
    transfers_out: int
    status: str
    chance_of_playing_next_round: int | None
    total_minutes: int = 0
    total_points: int = 0
    starts: int = 0
    points_per_game: float = 0.0
    form: float = 0.0
    expected_goals: float | None = None
    expected_assists: float | None = None


@dataclass(frozen=True)
class ProjectionComponentBreakdown:
    appearance_points: float
    goal_points: float
    assist_points: float
    clean_sheet_points: float
    bonus_points: float
    defensive_contribution_points: float
    other_points: float

    @property
    def total_points(self) -> float:
        return (
            self.appearance_points
            + self.goal_points
            + self.assist_points
            + self.clean_sheet_points
            + self.bonus_points
            + self.defensive_contribution_points
            + self.other_points
        )


@dataclass(frozen=True)
class Projection:
    player_id: int
    fixture_id: int | None
    gameweek_id: int | None
    projected_points: float
    expected_minutes: float
    generated_at: dt.datetime
    model_version: str
    components: ProjectionComponentBreakdown
