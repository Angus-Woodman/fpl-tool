from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import (
    PlayerPosition,
    Projection,
)
from fpl_engine.projections import BaselineProjectionModel, ProjectionInput

from api.services.projection_context import (
    RECENT_STATS_LIMIT,
    ProjectionGenerationContext,
    ProjectionSourceRepositoryPort,
    TeamStrengthRepositoryPort,
    fetch_projection_generation_context,
    gameweeks_covered,
    group_players_by_team,
)

DEFAULT_POINTS_PER_MINUTE: dict[PlayerPosition, float] = {
    PlayerPosition.GOALKEEPER: 0.045,
    PlayerPosition.DEFENDER: 0.048,
    PlayerPosition.MIDFIELDER: 0.06,
    PlayerPosition.FORWARD: 0.062,
}

HOME_FIXTURE_MULTIPLIER = 1.05
AWAY_FIXTURE_MULTIPLIER = 0.95


class ProjectionRepositoryPort(Protocol):
    def upsert_many(self, projections: list[Projection]) -> None: ...


class ProjectionRunRepositoryPort(Protocol):
    def create(
        self,
        *,
        model_version: str,
        generated_at: dt.datetime,
        gameweeks_covered: list[int],
        parameters: dict[str, object],
        team_strength_snapshot: dict[str, object],
        player_snapshot_generated_at: dt.datetime | None,
    ) -> int: ...


@dataclass(frozen=True)
class GenerateProjectionsSummary:
    projections_generated: int
    fixtures_considered: int
    players_considered: int
    model_version: str
    generated_at: dt.datetime
    run_id: int | None = None


class GenerateProjectionsService:
    def __init__(
        self,
        source_repository: ProjectionSourceRepositoryPort,
        projection_repository: ProjectionRepositoryPort,
        team_repository: TeamStrengthRepositoryPort,
        run_repository: ProjectionRunRepositoryPort,
        model: BaselineProjectionModel | None = None,
    ) -> None:
        self._source_repository = source_repository
        self._projection_repository = projection_repository
        self._team_repository = team_repository
        self._run_repository = run_repository
        self._model = model or BaselineProjectionModel()

    def fetch_context(self) -> ProjectionGenerationContext:
        """Fetches everything this model needs in one pass, so a dual-write caller
        can fetch once and feed the identical context to both baseline_v1 and
        baseline_v2."""
        return fetch_projection_generation_context(self._source_repository, self._team_repository)

    def execute(
        self, context: ProjectionGenerationContext | None = None
    ) -> GenerateProjectionsSummary:
        """Passing no context preserves this model's original, standalone
        behaviour exactly: fetch fresh, generate, persist. Passing a context
        (built via fetch_context(), typically shared with baseline_v2) skips the
        fetch and uses the supplied data instead."""
        if context is None:
            context = self.fetch_context()

        generated_at = context.generated_at
        fixtures = context.fixtures
        players = context.players
        players_by_team = group_players_by_team(players)

        run_id = self._run_repository.create(
            model_version=self._model.model_version,
            generated_at=generated_at,
            gameweeks_covered=gameweeks_covered(fixtures),
            parameters=self._build_parameters(),
            team_strength_snapshot=context.team_strength_snapshot,
            player_snapshot_generated_at=context.snapshot_generation,
        )

        projections: list[Projection] = []
        for fixture in fixtures:
            fixture_players = players_by_team.get(fixture.home_team_id, []) + players_by_team.get(
                fixture.away_team_id, []
            )
            for player in fixture_players:
                player_stats = context.recent_stats_by_player.get(player.id, [])
                recent_minutes = tuple(stat.minutes for stat in player_stats[:RECENT_STATS_LIMIT])
                total_minutes = sum(stat.minutes for stat in player_stats[:RECENT_STATS_LIMIT])
                total_points = sum(stat.total_points for stat in player_stats[:RECENT_STATS_LIMIT])
                points_per_minute = (
                    total_points / total_minutes
                    if total_minutes > 0
                    else DEFAULT_POINTS_PER_MINUTE[player.position]
                )
                snapshot = context.snapshots_by_player.get(player.id)
                availability_status = snapshot.status if snapshot is not None else player.status
                chance = snapshot.chance_of_playing_next_round if snapshot is not None else None
                fixture_multiplier = (
                    HOME_FIXTURE_MULTIPLIER
                    if player.team_id == fixture.home_team_id
                    else AWAY_FIXTURE_MULTIPLIER
                )

                projections.append(
                    dataclasses.replace(
                        self._model.project(
                            ProjectionInput(
                                player_id=player.id,
                                fixture_id=fixture.id,
                                gameweek_id=fixture.gameweek_id,
                                player_position=player.position,
                                points_per_minute=points_per_minute,
                                recent_minutes=recent_minutes,
                                fixture_difficulty_multiplier=fixture_multiplier,
                                availability_status=availability_status,
                                chance_of_playing_next_round=chance,
                                generated_at=generated_at,
                            )
                        ),
                        run_id=run_id,
                    )
                )

        self._projection_repository.upsert_many(projections)

        return GenerateProjectionsSummary(
            projections_generated=len(projections),
            fixtures_considered=len(fixtures),
            players_considered=len(players),
            model_version=self._model.model_version,
            generated_at=generated_at,
            run_id=run_id,
        )

    def _build_parameters(self) -> dict[str, object]:
        return {
            "model_version": self._model.model_version,
            "points_per_minute_defaults": {
                position.value: value for position, value in DEFAULT_POINTS_PER_MINUTE.items()
            },
            "recent_stats_limit": RECENT_STATS_LIMIT,
            "home_fixture_multiplier": HOME_FIXTURE_MULTIPLIER,
            "away_fixture_multiplier": AWAY_FIXTURE_MULTIPLIER,
        }
