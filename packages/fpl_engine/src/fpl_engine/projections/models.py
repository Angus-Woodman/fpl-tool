from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

from fpl_engine.domain import PlayerPosition, Projection, ProjectionComponentBreakdown

POSITION_COMPONENT_SHARES: dict[PlayerPosition, tuple[float, float, float, float, float, float]] = {
    PlayerPosition.GOALKEEPER: (0.65, 0.0, 0.02, 0.2, 0.08, 0.05),
    PlayerPosition.DEFENDER: (0.55, 0.08, 0.07, 0.18, 0.07, 0.05),
    PlayerPosition.MIDFIELDER: (0.42, 0.26, 0.16, 0.04, 0.08, 0.04),
    PlayerPosition.FORWARD: (0.4, 0.34, 0.13, 0.0, 0.08, 0.05),
}


STATUS_MULTIPLIERS: dict[str, float] = {
    "a": 1.0,
    "d": 0.75,
    "i": 0.0,
    "u": 0.0,
    "s": 0.0,
}


@dataclass(frozen=True)
class ProjectionInput:
    player_id: int
    fixture_id: int | None
    gameweek_id: int | None
    player_position: PlayerPosition
    points_per_minute: float
    recent_minutes: tuple[int, ...]
    fixture_difficulty_multiplier: float
    availability_status: str = "a"
    chance_of_playing_next_round: int | None = None
    generated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


class ProjectionModel(Protocol):
    model_version: str

    def estimate_expected_minutes(self, data: ProjectionInput) -> float: ...

    def project(self, data: ProjectionInput) -> Projection: ...

    def project_points(self, data: ProjectionInput) -> float: ...


@dataclass(frozen=True)
class BaselineProjectionModel:
    model_version: str = "baseline_v1"

    def estimate_expected_minutes(self, data: ProjectionInput) -> float:
        if data.recent_minutes:
            baseline_minutes = sum(data.recent_minutes) / len(data.recent_minutes)
        else:
            baseline_minutes = 75.0

        status_multiplier = STATUS_MULTIPLIERS.get(data.availability_status.lower(), 0.85)
        chance_multiplier = (
            1.0
            if data.chance_of_playing_next_round is None
            else max(0.0, min(100.0, float(data.chance_of_playing_next_round))) / 100.0
        )
        expected_minutes = baseline_minutes * status_multiplier * chance_multiplier
        return max(0.0, min(90.0, expected_minutes))

    def project(self, data: ProjectionInput) -> Projection:
        expected_minutes = self.estimate_expected_minutes(data)
        projected_points = (
            data.points_per_minute * expected_minutes * data.fixture_difficulty_multiplier
        )

        (
            appearance_share,
            goal_share,
            assist_share,
            clean_sheet_share,
            bonus_share,
            defensive_share,
        ) = POSITION_COMPONENT_SHARES[data.player_position]

        components = ProjectionComponentBreakdown(
            appearance_points=projected_points * appearance_share,
            goal_points=projected_points * goal_share,
            assist_points=projected_points * assist_share,
            clean_sheet_points=projected_points * clean_sheet_share,
            bonus_points=projected_points * bonus_share,
            defensive_contribution_points=projected_points * defensive_share,
            other_points=0.0,
        )

        return Projection(
            player_id=data.player_id,
            fixture_id=data.fixture_id,
            gameweek_id=data.gameweek_id,
            projected_points=projected_points,
            expected_minutes=expected_minutes,
            generated_at=data.generated_at,
            model_version=self.model_version,
            components=components,
        )

    def project_points(self, data: ProjectionInput) -> float:
        return self.project(data).projected_points
