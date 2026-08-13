from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import Fixture, Player, PlayerGameweekStat, PlayerSnapshot

from api.repositories.team_read_repository import TeamReadItem

RECENT_STATS_LIMIT = 3


class ProjectionSourceRepositoryPort(Protocol):
    def list_upcoming_fixtures(self) -> list[Fixture]: ...

    def list_players_for_team_ids(self, team_ids: set[int]) -> list[Player]: ...

    def list_recent_stats(self, player_ids: set[int]) -> list[PlayerGameweekStat]: ...

    def get_latest_snapshot_generation(self) -> dt.datetime | None: ...

    def list_snapshots_for_generation(
        self, player_ids: set[int], generated_at: dt.datetime
    ) -> list[PlayerSnapshot]: ...


class TeamStrengthRepositoryPort(Protocol):
    def list_teams(self) -> list[TeamReadItem]: ...


@dataclass(frozen=True)
class ProjectionGenerationContext:
    """Everything both baseline_v1 and baseline_v2 need to fetch exactly once and
    share, so a dual-write run cannot silently mix generations, timestamps, or
    team-strength readings between the two models."""

    generated_at: dt.datetime
    fixtures: list[Fixture]
    players: list[Player]
    recent_stats_by_player: dict[int, list[PlayerGameweekStat]]
    snapshot_generation: dt.datetime | None
    snapshots_by_player: dict[int, PlayerSnapshot]
    team_strength_snapshot: dict[str, object]


def fetch_projection_generation_context(
    source_repository: ProjectionSourceRepositoryPort,
    team_repository: TeamStrengthRepositoryPort,
) -> ProjectionGenerationContext:
    generated_at = dt.datetime.now(dt.UTC)
    fixtures = source_repository.list_upcoming_fixtures()
    team_ids = {
        team_id for fixture in fixtures for team_id in (fixture.home_team_id, fixture.away_team_id)
    }
    players = source_repository.list_players_for_team_ids(team_ids)
    player_ids = {player.id for player in players}

    recent_stats_by_player = _group_recent_stats(source_repository.list_recent_stats(player_ids))

    snapshot_generation = source_repository.get_latest_snapshot_generation()
    snapshots = (
        source_repository.list_snapshots_for_generation(player_ids, snapshot_generation)
        if snapshot_generation is not None
        else []
    )
    snapshots_by_player = {snapshot.player_id: snapshot for snapshot in snapshots}

    return ProjectionGenerationContext(
        generated_at=generated_at,
        fixtures=fixtures,
        players=players,
        recent_stats_by_player=recent_stats_by_player,
        snapshot_generation=snapshot_generation,
        snapshots_by_player=snapshots_by_player,
        team_strength_snapshot=build_team_strength_snapshot(team_repository),
    )


def group_players_by_team(players: list[Player]) -> dict[int, list[Player]]:
    grouped: dict[int, list[Player]] = defaultdict(list)
    for player in players:
        grouped[player.team_id].append(player)
    return grouped


def gameweeks_covered(fixtures: list[Fixture]) -> list[int]:
    return sorted({fixture.gameweek_id for fixture in fixtures if fixture.gameweek_id is not None})


def build_team_strength_snapshot(team_repository: TeamStrengthRepositoryPort) -> dict[str, object]:
    return {
        str(team.id): {
            "source_difficulty": team.source_difficulty,
            "override": team.difficulty_override,
            "effective_difficulty": team.difficulty,
        }
        for team in team_repository.list_teams()
    }


def _group_recent_stats(stats: list[PlayerGameweekStat]) -> dict[int, list[PlayerGameweekStat]]:
    grouped: dict[int, list[PlayerGameweekStat]] = defaultdict(list)
    for stat in stats:
        if len(grouped[stat.player_id]) < RECENT_STATS_LIMIT:
            grouped[stat.player_id].append(stat)
    return grouped
