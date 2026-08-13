from __future__ import annotations

import dataclasses
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import (
    Fixture,
    Player,
    PlayerGameweekStat,
    PlayerPosition,
    PlayerSnapshot,
    Projection,
)
from fpl_engine.projections import BaselineProjectionModel, ProjectionInput

from api.repositories.team_read_repository import TeamReadItem

DEFAULT_POINTS_PER_MINUTE: dict[PlayerPosition, float] = {
    PlayerPosition.GOALKEEPER: 0.045,
    PlayerPosition.DEFENDER: 0.048,
    PlayerPosition.MIDFIELDER: 0.06,
    PlayerPosition.FORWARD: 0.062,
}

HOME_FIXTURE_MULTIPLIER = 1.05
AWAY_FIXTURE_MULTIPLIER = 0.95
RECENT_STATS_LIMIT = 3


class ProjectionGenerationRepositoryPort(Protocol):
    def list_upcoming_fixtures(self) -> list[Fixture]: ...

    def list_players_for_team_ids(self, team_ids: set[int]) -> list[Player]: ...

    def list_recent_stats(self, player_ids: set[int]) -> list[PlayerGameweekStat]: ...

    def list_latest_snapshots(self, player_ids: set[int]) -> list[PlayerSnapshot]: ...


class ProjectionRepositoryPort(Protocol):
    def upsert_many(self, projections: list[Projection]) -> None: ...


class TeamStrengthRepositoryPort(Protocol):
    def list_teams(self) -> list[TeamReadItem]: ...


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


class GenerateProjectionsService:
    def __init__(
        self,
        source_repository: ProjectionGenerationRepositoryPort,
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

    def execute(self) -> GenerateProjectionsSummary:
        generated_at = dt.datetime.now(dt.UTC)
        fixtures = self._source_repository.list_upcoming_fixtures()
        team_ids = {
            team_id
            for fixture in fixtures
            for team_id in (fixture.home_team_id, fixture.away_team_id)
        }
        players = self._source_repository.list_players_for_team_ids(team_ids)
        players_by_team = self._group_players_by_team(players)

        player_ids = {player.id for player in players}
        recent_stats_by_player = self._group_recent_stats(
            self._source_repository.list_recent_stats(player_ids)
        )
        snapshots = self._source_repository.list_latest_snapshots(player_ids)
        snapshots_by_player = {snapshot.player_id: snapshot for snapshot in snapshots}

        run_id = self._run_repository.create(
            model_version=self._model.model_version,
            generated_at=generated_at,
            gameweeks_covered=sorted(
                {fixture.gameweek_id for fixture in fixtures if fixture.gameweek_id is not None}
            ),
            parameters=self._build_parameters(),
            team_strength_snapshot=self._build_team_strength_snapshot(),
            player_snapshot_generated_at=(
                max(snapshot.captured_at for snapshot in snapshots) if snapshots else None
            ),
        )

        projections: list[Projection] = []
        for fixture in fixtures:
            fixture_players = players_by_team.get(fixture.home_team_id, []) + players_by_team.get(
                fixture.away_team_id, []
            )
            for player in fixture_players:
                player_stats = recent_stats_by_player.get(player.id, [])
                recent_minutes = tuple(stat.minutes for stat in player_stats[:RECENT_STATS_LIMIT])
                total_minutes = sum(stat.minutes for stat in player_stats[:RECENT_STATS_LIMIT])
                total_points = sum(stat.total_points for stat in player_stats[:RECENT_STATS_LIMIT])
                points_per_minute = (
                    total_points / total_minutes
                    if total_minutes > 0
                    else DEFAULT_POINTS_PER_MINUTE[player.position]
                )
                snapshot = snapshots_by_player.get(player.id)
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
        )

    def _group_players_by_team(self, players: list[Player]) -> dict[int, list[Player]]:
        grouped: dict[int, list[Player]] = defaultdict(list)
        for player in players:
            grouped[player.team_id].append(player)
        return grouped

    def _group_recent_stats(
        self, stats: list[PlayerGameweekStat]
    ) -> dict[int, list[PlayerGameweekStat]]:
        grouped: dict[int, list[PlayerGameweekStat]] = defaultdict(list)
        for stat in stats:
            if len(grouped[stat.player_id]) < RECENT_STATS_LIMIT:
                grouped[stat.player_id].append(stat)
        return grouped

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

    def _build_team_strength_snapshot(self) -> dict[str, object]:
        return {
            str(team.id): {
                "source_difficulty": team.source_difficulty,
                "override": team.difficulty_override,
                "effective_difficulty": team.difficulty,
            }
            for team in self._team_repository.list_teams()
        }
