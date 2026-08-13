from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fpl_engine.domain import PlayerPosition, Projection, ProjectionComponentBreakdown
from fpl_engine.projections.shrinkage import shrink_rate

# FROZEN for prospective evaluation once operational (mirrors baseline_v2's
# policy): material formula/parameter changes belong in a new model_version,
# not a mutation of "component_v3". Deliberately self-contained -- does not
# import from fpl_engine.projections.baseline_v2 -- so v2 stays untouched and
# the two models can never accidentally couple.

if TYPE_CHECKING:
    from fpl_engine.minutes import ExpectedMinutesResult

APPEARANCE_POINT_VALUE = 1.0
SIXTY_MINUTE_POINT_VALUE = 1.0

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

# FPL scoring rules, not derived from data -- confirm against current rules
# before relying on these in a real season.
CLEAN_SHEET_POINTS_DEFAULT: dict[PlayerPosition, float] = {
    PlayerPosition.GOALKEEPER: 4.0,
    PlayerPosition.DEFENDER: 4.0,
    PlayerPosition.MIDFIELDER: 1.0,
    PlayerPosition.FORWARD: 0.0,
}

# Coarse, unvalidated, and deliberately separate from DIFFICULTY_MULTIPLIERS_DEFAULT
# above (opponent defensive difficulty -> attacking returns): this table maps
# opponent ATTACKING strength -> our clean-sheet probability. They currently
# both derive from the same single source-strength signal (no separate
# attack/defence sub-ratings are captured), but are independently
# parameterised and must not be conflated or inverted from one another.
OPPONENT_ATTACK_MULTIPLIERS_FOR_CLEAN_SHEETS_DEFAULT: dict[int, float] = {
    1: 1.2,
    2: 1.1,
    3: 1.0,
    4: 0.9,
    5: 0.75,
}
HOME_CLEAN_SHEET_MULTIPLIER_DEFAULT = 1.10
AWAY_CLEAN_SHEET_MULTIPLIER_DEFAULT = 0.90


@dataclass(frozen=True)
class ComponentV3PositionPriors:
    """Cohort/position-level productivity priors, supplied by the caller from real data.

    `saves_per_90` is only meaningful for GOALKEEPER; other positions carry a
    default of 0.0 and are simply never used, since goalkeeper saves are the
    only position that scores save points.
    """

    expected_goals_per_90: float
    expected_assists_per_90: float
    saves_per_90: float = 0.0


@dataclass(frozen=True)
class ComponentV3Parameters:
    xg90_m0: float = 900.0
    xa90_m0: float = 900.0
    goal_points: Mapping[PlayerPosition, float] = field(
        default_factory=lambda: dict(GOAL_POINTS_DEFAULT)
    )
    assist_points: float = ASSIST_POINTS_DEFAULT
    # Keyed by the OPPONENT's *source* strength (never a manual override) --
    # see api.services.component_v3_projections for where this is resolved.
    difficulty_multipliers: Mapping[int, float] = field(
        default_factory=lambda: dict(DIFFICULTY_MULTIPLIERS_DEFAULT)
    )
    home_venue_multiplier: float = HOME_VENUE_MULTIPLIER_DEFAULT
    away_venue_multiplier: float = AWAY_VENUE_MULTIPLIER_DEFAULT
    saves_m0: float = 900.0
    clean_sheet_points: Mapping[PlayerPosition, float] = field(
        default_factory=lambda: dict(CLEAN_SHEET_POINTS_DEFAULT)
    )
    opponent_attack_multipliers_for_clean_sheets: Mapping[int, float] = field(
        default_factory=lambda: dict(OPPONENT_ATTACK_MULTIPLIERS_FOR_CLEAN_SHEETS_DEFAULT)
    )
    home_clean_sheet_multiplier: float = HOME_CLEAN_SHEET_MULTIPLIER_DEFAULT
    away_clean_sheet_multiplier: float = AWAY_CLEAN_SHEET_MULTIPLIER_DEFAULT


DEFAULT_COMPONENT_V3_PARAMETERS = ComponentV3Parameters()


@dataclass(frozen=True)
class ComponentV3Input:
    player_id: int
    fixture_id: int | None
    gameweek_id: int | None
    position: PlayerPosition
    expected_minutes: ExpectedMinutesResult
    expected_goals_per_90: float
    expected_assists_per_90: float
    total_minutes: float
    saves_per_90: float
    # Pre-resolved via fpl_engine.projections.component_v3_priors.compute_team_defense_priors
    # (already shrunk toward a source-strength-derived prior for this player's own team).
    own_team_clean_sheet_rate: float
    # The OPPONENT's source strength -- deliberately never the manual
    # difficulty override, so this objective model cannot be silently altered
    # by a fixture-ticker edit.
    opponent_source_difficulty: int
    is_home: bool
    generated_at: dt.datetime


@dataclass(frozen=True)
class ComponentV3Explanation:
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
    team_clean_sheet_probability_raw: float
    team_clean_sheet_probability: float
    team_clean_sheet_probability_was_clamped: bool
    clean_sheet_points: float
    raw_saves_per_90: float
    shrunk_saves_per_90: float
    saves_observed_history_weight: float
    expected_saves: float
    expected_save_points: float
    total_points: float


@dataclass(frozen=True)
class ComponentV3ProjectionModel:
    priors: Mapping[PlayerPosition, ComponentV3PositionPriors]
    parameters: ComponentV3Parameters = DEFAULT_COMPONENT_V3_PARAMETERS
    model_version: str = "component_v3"

    def explain(self, data: ComponentV3Input) -> ComponentV3Explanation:
        priors = self.priors[data.position]

        if data.opponent_source_difficulty not in self.parameters.difficulty_multipliers:
            raise ValueError(f"Unrecognised difficulty: {data.opponent_source_difficulty}")
        if (
            data.opponent_source_difficulty
            not in self.parameters.opponent_attack_multipliers_for_clean_sheets
        ):
            raise ValueError(
                "Unrecognised opponent-attack difficulty for clean sheets: "
                f"{data.opponent_source_difficulty}"
            )

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

        probability_of_playing = data.expected_minutes.probability_of_playing
        probability_60_plus = data.expected_minutes.probability_60_plus

        venue_multiplier = (
            self.parameters.home_venue_multiplier
            if data.is_home
            else self.parameters.away_venue_multiplier
        )
        difficulty_multiplier = self.parameters.difficulty_multipliers[
            data.opponent_source_difficulty
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

        cs_venue_multiplier = (
            self.parameters.home_clean_sheet_multiplier
            if data.is_home
            else self.parameters.away_clean_sheet_multiplier
        )
        cs_opponent_multiplier = self.parameters.opponent_attack_multipliers_for_clean_sheets[
            data.opponent_source_difficulty
        ]
        team_clean_sheet_probability_raw = (
            data.own_team_clean_sheet_rate * cs_opponent_multiplier * cs_venue_multiplier
        )
        team_clean_sheet_probability = min(1.0, max(0.0, team_clean_sheet_probability_raw))
        team_clean_sheet_probability_was_clamped = (
            team_clean_sheet_probability != team_clean_sheet_probability_raw
        )
        clean_sheet_points = (
            team_clean_sheet_probability
            * probability_60_plus
            * self.parameters.clean_sheet_points[data.position]
        )

        if data.position == PlayerPosition.GOALKEEPER:
            saves = shrink_rate(
                observed_rate=data.saves_per_90,
                sample_weight=data.total_minutes,
                prior_rate=priors.saves_per_90,
                prior_weight=self.parameters.saves_m0,
            )
            raw_saves_per_90 = data.saves_per_90
            shrunk_saves_per_90 = saves.value
            saves_observed_history_weight = saves.observed_share
            expected_saves = shrunk_saves_per_90 * minutes_fraction
            expected_save_points = expected_saves / 3
        else:
            raw_saves_per_90 = 0.0
            shrunk_saves_per_90 = 0.0
            saves_observed_history_weight = 0.0
            expected_saves = 0.0
            expected_save_points = 0.0

        total_points = (
            appearance_points
            + goal_points
            + assist_points
            + clean_sheet_points
            + expected_save_points
        )

        return ComponentV3Explanation(
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
            team_clean_sheet_probability_raw=team_clean_sheet_probability_raw,
            team_clean_sheet_probability=team_clean_sheet_probability,
            team_clean_sheet_probability_was_clamped=team_clean_sheet_probability_was_clamped,
            clean_sheet_points=clean_sheet_points,
            raw_saves_per_90=raw_saves_per_90,
            shrunk_saves_per_90=shrunk_saves_per_90,
            saves_observed_history_weight=saves_observed_history_weight,
            expected_saves=expected_saves,
            expected_save_points=expected_save_points,
            total_points=total_points,
        )

    def project(self, data: ComponentV3Input) -> Projection:
        explanation = self.explain(data)

        components = ProjectionComponentBreakdown(
            appearance_points=explanation.appearance_points,
            goal_points=explanation.goal_points,
            assist_points=explanation.assist_points,
            clean_sheet_points=explanation.clean_sheet_points,
            bonus_points=0.0,
            defensive_contribution_points=0.0,
            other_points=0.0,
            save_points=explanation.expected_save_points,
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

    def project_points(self, data: ComponentV3Input) -> float:
        return self.project(data).projected_points
