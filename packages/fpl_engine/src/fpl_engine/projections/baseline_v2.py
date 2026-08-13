from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fpl_engine.domain import PlayerPosition, Projection, ProjectionComponentBreakdown
from fpl_engine.projections.shrinkage import shrink_rate

if TYPE_CHECKING:
    # Deferred: fpl_engine.minutes imports fpl_engine.projections.shrinkage, so a
    # runtime import here would be circular. Only used as a type annotation.
    from fpl_engine.minutes import ExpectedMinutesResult

APPEARANCE_POINT_VALUE = 1.0
SIXTY_MINUTE_POINT_VALUE = 1.0
P60_TOLERANCE = 1e-9

GOAL_POINTS_DEFAULT: dict[PlayerPosition, float] = {
    PlayerPosition.GOALKEEPER: 6.0,
    PlayerPosition.DEFENDER: 6.0,
    PlayerPosition.MIDFIELDER: 5.0,
    PlayerPosition.FORWARD: 4.0,
}
ASSIST_POINTS_DEFAULT = 3.0

DIFFICULTY_MULTIPLIERS_DEFAULT: dict[int, float] = {1: 1.15, 2: 1.075, 3: 1.0, 4: 0.925, 5: 0.85}
HOME_VENUE_MULTIPLIER_DEFAULT = 1.05
AWAY_VENUE_MULTIPLIER_DEFAULT = 0.95


@dataclass(frozen=True)
class BaselineV2PositionPriors:
    """Cohort/position-level priors, supplied by the caller from real data.

    `sub_appearance_probability` is a coarse, pre-season, position-level assumption
    -- P(comes on as a substitute | did not start) -- used only because no
    player-specific version of it is identifiable before in-season (started,
    minutes) observations exist (see fpl_engine.minutes, Slice 1.5c).
    """

    expected_goals_per_90: float
    expected_assists_per_90: float
    sub_appearance_probability: float


@dataclass(frozen=True)
class BaselineV2Parameters:
    xg90_m0: float = 900.0
    xa90_m0: float = 900.0
    goal_points: Mapping[PlayerPosition, float] = field(
        default_factory=lambda: dict(GOAL_POINTS_DEFAULT)
    )
    assist_points: float = ASSIST_POINTS_DEFAULT
    # FPL's overall team-strength rating is used here as a proxy for opponent
    # defensive difficulty. It has not been validated as a genuine defensive
    # strength signal -- backtest before trusting this mapping.
    difficulty_multipliers: Mapping[int, float] = field(
        default_factory=lambda: dict(DIFFICULTY_MULTIPLIERS_DEFAULT)
    )
    home_venue_multiplier: float = HOME_VENUE_MULTIPLIER_DEFAULT
    away_venue_multiplier: float = AWAY_VENUE_MULTIPLIER_DEFAULT


DEFAULT_BASELINE_V2_PARAMETERS = BaselineV2Parameters()


@dataclass(frozen=True)
class BaselineV2Input:
    player_id: int
    fixture_id: int | None
    gameweek_id: int | None
    position: PlayerPosition
    expected_minutes: ExpectedMinutesResult
    expected_goals_per_90: float
    expected_assists_per_90: float
    total_minutes: float
    opponent_effective_difficulty: int
    is_home: bool
    generated_at: dt.datetime


@dataclass(frozen=True)
class BaselineV2Explanation:
    """Enough detail to answer "why did this projection come out this way?"."""

    player_id: int
    probability_of_playing: float
    probability_60_plus: float
    expected_minutes: float
    shrunk_expected_goals_per_90: float
    shrunk_expected_assists_per_90: float
    goals_observed_history_weight: float
    assists_observed_history_weight: float
    venue_multiplier: float
    difficulty_multiplier: float
    appearance_points: float
    goal_points: float
    assist_points: float
    total_points: float


@dataclass(frozen=True)
class BaselineV2ProjectionModel:
    priors: Mapping[PlayerPosition, BaselineV2PositionPriors]
    parameters: BaselineV2Parameters = DEFAULT_BASELINE_V2_PARAMETERS
    model_version: str = "baseline_v2"

    def explain(self, data: BaselineV2Input) -> BaselineV2Explanation:
        priors = self.priors[data.position]

        if data.opponent_effective_difficulty not in self.parameters.difficulty_multipliers:
            raise ValueError(f"Unrecognised difficulty: {data.opponent_effective_difficulty}")

        goals = shrink_rate(
            observed_rate=data.expected_goals_per_90,
            sample_weight=data.total_minutes,
            prior_rate=priors.expected_goals_per_90,
            prior_weight=self.parameters.xg90_m0,
        )
        assists = shrink_rate(
            observed_rate=data.expected_assists_per_90,
            sample_weight=data.total_minutes,
            prior_rate=priors.expected_assists_per_90,
            prior_weight=self.parameters.xa90_m0,
        )

        start_probability = data.expected_minutes.start_probability
        probability_of_playing = (
            start_probability + (1 - start_probability) * priors.sub_appearance_probability
        )
        probability_60_plus = data.expected_minutes.probability_60_plus

        if probability_60_plus > probability_of_playing + P60_TOLERANCE:
            raise ValueError(
                "P(60+) exceeds P(play): "
                f"{probability_60_plus} > {probability_of_playing}. "
                "The supplied priors are inconsistent."
            )

        venue_multiplier = (
            self.parameters.home_venue_multiplier
            if data.is_home
            else self.parameters.away_venue_multiplier
        )
        difficulty_multiplier = self.parameters.difficulty_multipliers[
            data.opponent_effective_difficulty
        ]
        fixture_multiplier = venue_multiplier * difficulty_multiplier
        minutes_fraction = data.expected_minutes.expected_minutes / 90

        appearance_points = (
            probability_of_playing * APPEARANCE_POINT_VALUE
            + probability_60_plus * SIXTY_MINUTE_POINT_VALUE
        )
        goal_points = (
            goals.value
            * minutes_fraction
            * self.parameters.goal_points[data.position]
            * fixture_multiplier
        )
        assist_points = (
            assists.value * minutes_fraction * self.parameters.assist_points * fixture_multiplier
        )

        return BaselineV2Explanation(
            player_id=data.player_id,
            probability_of_playing=probability_of_playing,
            probability_60_plus=probability_60_plus,
            expected_minutes=data.expected_minutes.expected_minutes,
            shrunk_expected_goals_per_90=goals.value,
            shrunk_expected_assists_per_90=assists.value,
            goals_observed_history_weight=goals.observed_share,
            assists_observed_history_weight=assists.observed_share,
            venue_multiplier=venue_multiplier,
            difficulty_multiplier=difficulty_multiplier,
            appearance_points=appearance_points,
            goal_points=goal_points,
            assist_points=assist_points,
            total_points=appearance_points + goal_points + assist_points,
        )

    def project(self, data: BaselineV2Input) -> Projection:
        explanation = self.explain(data)

        components = ProjectionComponentBreakdown(
            appearance_points=explanation.appearance_points,
            goal_points=explanation.goal_points,
            assist_points=explanation.assist_points,
            clean_sheet_points=0.0,
            bonus_points=0.0,
            defensive_contribution_points=0.0,
            other_points=0.0,
        )

        return Projection(
            player_id=data.player_id,
            fixture_id=data.fixture_id,
            gameweek_id=data.gameweek_id,
            projected_points=explanation.total_points,
            expected_minutes=explanation.expected_minutes,
            generated_at=data.generated_at,
            model_version=self.model_version,
            components=components,
        )

    def project_points(self, data: BaselineV2Input) -> float:
        return self.project(data).projected_points
