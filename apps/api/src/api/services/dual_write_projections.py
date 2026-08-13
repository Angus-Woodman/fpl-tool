from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fpl_engine.domain import PlayerPosition, Projection
from fpl_engine.minutes import (
    DEFAULT_PRE_SEASON_PARAMETERS,
    PreSeasonMinutesParameters,
    RoleLabel,
    estimate_pre_season_expected_minutes,
)
from fpl_engine.projections import (
    DEFAULT_BASELINE_V2_PARAMETERS,
    DEFAULT_PRIOR_COMPUTATION_PARAMETERS,
    BaselineV2Input,
    BaselineV2Parameters,
    BaselineV2Priors,
    BaselineV2ProjectionModel,
    ConfiguredPositionAssumptions,
    PlayerHistoryForPriors,
    PriorComputationParameters,
    compute_baseline_v2_priors,
)

from api.services.generate_projections import (
    GenerateProjectionsService,
    GenerateProjectionsSummary,
    ProjectionRepositoryPort,
    ProjectionRunRepositoryPort,
)
from api.services.projection_context import (
    ProjectionSourceRepositoryPort,
    TeamStrengthRepositoryPort,
    fetch_projection_generation_context,
    gameweeks_covered,
    group_players_by_team,
)

# Configuration-derived assumptions the available data cannot separate out (see
# fpl_engine.projections.baseline_v2_priors): never computed from aggregates,
# always a judgment call pending backtesting.
DEFAULT_CONFIGURED_ASSUMPTIONS: dict[PlayerPosition, ConfiguredPositionAssumptions] = {
    PlayerPosition.GOALKEEPER: ConfiguredPositionAssumptions(
        minutes_if_start=90.0,
        sub_appearance_probability=0.01,
        minutes_if_sub=5.0,
        start_rate_fallback=0.5,
    ),
    PlayerPosition.DEFENDER: ConfiguredPositionAssumptions(
        minutes_if_start=88.0,
        sub_appearance_probability=0.15,
        minutes_if_sub=20.0,
        start_rate_fallback=0.45,
    ),
    PlayerPosition.MIDFIELDER: ConfiguredPositionAssumptions(
        minutes_if_start=85.0,
        sub_appearance_probability=0.25,
        minutes_if_sub=22.0,
        start_rate_fallback=0.4,
    ),
    PlayerPosition.FORWARD: ConfiguredPositionAssumptions(
        minutes_if_start=82.0,
        sub_appearance_probability=0.3,
        minutes_if_sub=25.0,
        start_rate_fallback=0.35,
    ),
}

DEFAULT_PROBABILITY_60_PLUS_BY_ROLE: dict[RoleLabel, float] = {
    # RoleLabel is derived purely from start_probability (see
    # fpl_engine.minutes.expected_minutes._role_label), independent of position,
    # and estimate_pre_season_expected_minutes() raises if a role's P60 prior
    # ever exceeds a specific player's computed P(play). Each value below is
    # kept safely under the *lowest* P(play) reachable at that role's bucket
    # boundary (using goalkeepers' low sub_appearance_probability=0.01 as the
    # conservative case, since any position can in principle land in any
    # bucket): NAILED >= 30/38 (~0.79), REGULAR >= 15/38 (~0.39), ROTATION_RISK
    # >= 5/38 (~0.13), FRINGE >= 1/38 (~0.03).
    RoleLabel.NAILED: 0.65,
    RoleLabel.REGULAR: 0.3,
    RoleLabel.ROTATION_RISK: 0.1,
    RoleLabel.FRINGE: 0.02,
    RoleLabel.UNKNOWN: 0.15,
    RoleLabel.NEW_TO_CLUB: 0.15,
}
DEFAULT_PROBABILITY_60_PLUS_DEFAULT = 0.15

# If more than this fraction of the fixture-relevant player pool has no
# player_snapshots row in the selected generation, baseline_v2 refuses to run
# rather than produce a materially incomplete comparison against baseline_v1.
MAX_MISSING_SNAPSHOT_FRACTION_DEFAULT = 0.5


class MissingSnapshotCoverageError(RuntimeError):
    """Raised when too many fixture-relevant players have no snapshot in the
    selected generation. Never falls back to an older generation -- it fails
    instead."""


@dataclass(frozen=True)
class DualWriteSummary:
    generated_at: dt.datetime
    snapshot_generation: dt.datetime | None
    v1: GenerateProjectionsSummary
    v1_run_id: int
    v2_run_id: int
    v2_projections_generated: int
    v2_players_considered: int
    v2_players_skipped_missing_snapshot: int
    v2_missing_snapshot_fraction: float


class DualWriteProjectionsService:
    """Runs baseline_v1 and baseline_v2 from one shared fetch.

    Both models consume the same snapshot generation, the same fixture/team
    load, the same resolved BaselineV2Priors, and the same `generated_at` --
    they cannot silently diverge on any of these. baseline_v1's own calculation
    logic is untouched; this orchestrator only supplies it a pre-fetched
    context instead of letting it fetch independently.
    """

    def __init__(
        self,
        *,
        source_repository: ProjectionSourceRepositoryPort,
        projection_repository: ProjectionRepositoryPort,
        team_repository: TeamStrengthRepositoryPort,
        run_repository: ProjectionRunRepositoryPort,
        v1_service: GenerateProjectionsService,
        v2_parameters: BaselineV2Parameters = DEFAULT_BASELINE_V2_PARAMETERS,
        configured_assumptions: Mapping[PlayerPosition, ConfiguredPositionAssumptions]
        | None = None,
        probability_60_plus_by_role: Mapping[RoleLabel, float] | None = None,
        probability_60_plus_default: float = DEFAULT_PROBABILITY_60_PLUS_DEFAULT,
        prior_computation_parameters: PriorComputationParameters = (
            DEFAULT_PRIOR_COMPUTATION_PARAMETERS
        ),
        expected_minutes_parameters: PreSeasonMinutesParameters = DEFAULT_PRE_SEASON_PARAMETERS,
        max_missing_snapshot_fraction: float = MAX_MISSING_SNAPSHOT_FRACTION_DEFAULT,
    ) -> None:
        self._source_repository = source_repository
        self._projection_repository = projection_repository
        self._team_repository = team_repository
        self._run_repository = run_repository
        self._v1_service = v1_service
        self._v2_parameters = v2_parameters
        self._configured_assumptions = dict(
            configured_assumptions or DEFAULT_CONFIGURED_ASSUMPTIONS
        )
        self._probability_60_plus_by_role = dict(
            probability_60_plus_by_role or DEFAULT_PROBABILITY_60_PLUS_BY_ROLE
        )
        self._probability_60_plus_default = probability_60_plus_default
        self._prior_computation_parameters = prior_computation_parameters
        self._expected_minutes_parameters = expected_minutes_parameters
        self._max_missing_snapshot_fraction = max_missing_snapshot_fraction

    def execute(self) -> DualWriteSummary:
        context = fetch_projection_generation_context(
            self._source_repository, self._team_repository
        )

        players_with_snapshot = [
            player for player in context.players if player.id in context.snapshots_by_player
        ]
        missing_count = len(context.players) - len(players_with_snapshot)
        missing_fraction = missing_count / len(context.players) if context.players else 0.0

        if missing_fraction > self._max_missing_snapshot_fraction:
            raise MissingSnapshotCoverageError(
                f"baseline_v2 refuses to run: {missing_count}/{len(context.players)} "
                f"fixture-relevant players ({missing_fraction:.1%}) have no "
                f"player_snapshots row in generation {context.snapshot_generation!r}. "
                "Never falling back to an older generation for the missing players; "
                f"the allowed threshold is {self._max_missing_snapshot_fraction:.1%}."
            )

        as_of = context.generated_at.date()
        histories = [
            PlayerHistoryForPriors(
                position=player.position,
                total_minutes=float(context.snapshots_by_player[player.id].total_minutes),
                expected_goals=context.snapshots_by_player[player.id].expected_goals or 0.0,
                expected_assists=context.snapshots_by_player[player.id].expected_assists or 0.0,
                starts=context.snapshots_by_player[player.id].starts,
                team_join_date=context.snapshots_by_player[player.id].team_join_date,
            )
            for player in players_with_snapshot
        ]
        priors = compute_baseline_v2_priors(
            histories,
            as_of=as_of,
            configured_assumptions=self._configured_assumptions,
            probability_60_plus_by_role=self._probability_60_plus_by_role,
            probability_60_plus_default=self._probability_60_plus_default,
            parameters=self._prior_computation_parameters,
        )

        v1_summary = self._v1_service.execute(context)
        assert v1_summary.run_id is not None

        v2_model = BaselineV2ProjectionModel(
            priors={
                position: priors.to_baseline_v2_position_priors(position)
                for position in priors.by_position
            },
            parameters=self._v2_parameters,
        )

        v2_run_id = self._run_repository.create(
            model_version=v2_model.model_version,
            generated_at=context.generated_at,
            gameweeks_covered=gameweeks_covered(context.fixtures),
            parameters=self._build_v2_parameters(
                priors, missing_count=missing_count, missing_fraction=missing_fraction
            ),
            team_strength_snapshot=context.team_strength_snapshot,
            player_snapshot_generated_at=context.snapshot_generation,
        )

        players_by_team = group_players_by_team(context.players)
        v2_projections: list[Projection] = []
        for fixture in context.fixtures:
            fixture_players = players_by_team.get(fixture.home_team_id, []) + players_by_team.get(
                fixture.away_team_id, []
            )
            for player in fixture_players:
                snapshot = context.snapshots_by_player.get(player.id)
                if snapshot is None or player.position not in priors.by_position:
                    continue

                is_home = player.team_id == fixture.home_team_id
                opponent_team_id = fixture.away_team_id if is_home else fixture.home_team_id
                opponent_strength = cast(
                    "dict[str, object]",
                    context.team_strength_snapshot[str(opponent_team_id)],
                )
                opponent_difficulty = cast(int, opponent_strength["effective_difficulty"])

                expected_minutes = estimate_pre_season_expected_minutes(
                    starts=snapshot.starts,
                    team_join_date=snapshot.team_join_date,
                    as_of=as_of,
                    status=snapshot.status,
                    chance_of_playing_next_round=snapshot.chance_of_playing_next_round,
                    priors=priors.to_pre_season_role_priors(player.position),
                    parameters=self._expected_minutes_parameters,
                )

                v2_input = BaselineV2Input(
                    player_id=player.id,
                    fixture_id=fixture.id,
                    gameweek_id=fixture.gameweek_id,
                    position=player.position,
                    expected_minutes=expected_minutes,
                    expected_goals_per_90=snapshot.expected_goals_per_90 or 0.0,
                    expected_assists_per_90=snapshot.expected_assists_per_90 or 0.0,
                    total_minutes=float(snapshot.total_minutes),
                    opponent_effective_difficulty=opponent_difficulty,
                    is_home=is_home,
                    generated_at=context.generated_at,
                )
                v2_projections.append(
                    dataclasses.replace(v2_model.project(v2_input), run_id=v2_run_id)
                )

        self._projection_repository.upsert_many(v2_projections)

        return DualWriteSummary(
            generated_at=context.generated_at,
            snapshot_generation=context.snapshot_generation,
            v1=v1_summary,
            v1_run_id=v1_summary.run_id,
            v2_run_id=v2_run_id,
            v2_projections_generated=len(v2_projections),
            v2_players_considered=len(players_with_snapshot),
            v2_players_skipped_missing_snapshot=missing_count,
            v2_missing_snapshot_fraction=missing_fraction,
        )

    def _build_v2_parameters(
        self, priors: BaselineV2Priors, *, missing_count: int, missing_fraction: float
    ) -> dict[str, object]:
        return {
            "model_version": "baseline_v2",
            "baseline_v2_parameters": {
                "xg90_m0": self._v2_parameters.xg90_m0,
                "xa90_m0": self._v2_parameters.xa90_m0,
                "goal_points": {
                    position.value: value
                    for position, value in self._v2_parameters.goal_points.items()
                },
                "assist_points": self._v2_parameters.assist_points,
                "difficulty_multipliers": dict(self._v2_parameters.difficulty_multipliers),
                "home_venue_multiplier": self._v2_parameters.home_venue_multiplier,
                "away_venue_multiplier": self._v2_parameters.away_venue_multiplier,
            },
            "prior_computation_parameters": {
                "minimum_minutes_for_cohort_inclusion": (
                    self._prior_computation_parameters.minimum_minutes_for_cohort_inclusion
                ),
                "minimum_cohort_size": self._prior_computation_parameters.minimum_cohort_size,
                "established_cutoff_months": (
                    self._prior_computation_parameters.established_cutoff_months
                ),
            },
            "expected_minutes_parameters": {
                "established_cutoff_months": (
                    self._expected_minutes_parameters.established_cutoff_months
                ),
                "m0_start_rate": self._expected_minutes_parameters.m0_start_rate,
                "high_confidence_starts": self._expected_minutes_parameters.high_confidence_starts,
                "nailed_threshold": self._expected_minutes_parameters.nailed_threshold,
                "regular_threshold": self._expected_minutes_parameters.regular_threshold,
                "rotation_threshold": self._expected_minutes_parameters.rotation_threshold,
                "fringe_threshold": self._expected_minutes_parameters.fringe_threshold,
            },
            "configured_position_assumptions": {
                position.value: {
                    "minutes_if_start": assumptions.minutes_if_start,
                    "sub_appearance_probability": assumptions.sub_appearance_probability,
                    "minutes_if_sub": assumptions.minutes_if_sub,
                    "start_rate_fallback": assumptions.start_rate_fallback,
                }
                for position, assumptions in self._configured_assumptions.items()
            },
            "resolved_priors_by_position": {
                position.value: {
                    "expected_goals_per_90": resolved.expected_goals_per_90,
                    "expected_assists_per_90": resolved.expected_assists_per_90,
                    "start_rate": resolved.start_rate,
                    "start_rate_is_fallback": resolved.start_rate_is_fallback,
                    "minutes_if_start": resolved.minutes_if_start,
                    "sub_appearance_probability": resolved.sub_appearance_probability,
                    "minutes_if_sub": resolved.minutes_if_sub,
                }
                for position, resolved in priors.by_position.items()
            },
            "probability_60_plus_by_role": {
                role.value: value for role, value in self._probability_60_plus_by_role.items()
            },
            "probability_60_plus_default": self._probability_60_plus_default,
            "missing_snapshot_players": missing_count,
            "missing_snapshot_fraction": missing_fraction,
            "max_missing_snapshot_fraction": self._max_missing_snapshot_fraction,
        }
