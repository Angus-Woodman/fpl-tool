from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import Fixture, Gameweek, Player, PlayerSnapshot, Team

from api.adapters.fpl import BootstrapStaticDto, FplFixtureDto, map_bootstrap_static, map_fixtures
from api.adapters.fpl.mappers import map_player_snapshots
from api.core.exceptions import DataMappingError


class BootstrapStaticProvider(Protocol):
    def fetch_bootstrap_static(self) -> BootstrapStaticDto: ...

    def fetch_fixtures(self) -> list[FplFixtureDto]: ...


class TeamRepositoryPort(Protocol):
    def upsert_many(self, teams: list[Team]) -> None: ...

    def get_internal_ids_by_external_ids(self, external_ids: set[int]) -> dict[int, int]: ...


class PlayerRepositoryPort(Protocol):
    def upsert_many(self, players: list[Player]) -> None: ...

    def get_internal_ids_by_external_ids(self, external_ids: set[int]) -> dict[int, int]: ...


class PlayerSnapshotRepositoryPort(Protocol):
    def upsert_many(self, snapshots: list[PlayerSnapshot]) -> None: ...


class GameweekRepositoryPort(Protocol):
    def upsert_many(self, gameweeks: list[Gameweek]) -> None: ...

    def get_internal_ids_by_numbers(self, numbers: set[int]) -> dict[int, int]: ...


class FixtureRepositoryPort(Protocol):
    def upsert_many(self, fixtures: list[Fixture]) -> None: ...


@dataclass(frozen=True)
class ImportSummary:
    teams_imported: int
    players_imported: int
    gameweeks_imported: int
    fixtures_imported: int
    player_snapshots_captured: int = 0


class ImportFplDataService:
    def __init__(
        self,
        provider: BootstrapStaticProvider,
        team_repository: TeamRepositoryPort,
        player_repository: PlayerRepositoryPort,
        gameweek_repository: GameweekRepositoryPort,
        fixture_repository: FixtureRepositoryPort,
        player_snapshot_repository: PlayerSnapshotRepositoryPort,
    ) -> None:
        self._provider = provider
        self._team_repository = team_repository
        self._player_repository = player_repository
        self._gameweek_repository = gameweek_repository
        self._fixture_repository = fixture_repository
        self._player_snapshot_repository = player_snapshot_repository

    def import_bootstrap_static(self) -> ImportSummary:
        payload = self._provider.fetch_bootstrap_static()
        mapped = map_bootstrap_static(payload)

        self._team_repository.upsert_many(mapped.teams)

        team_map = self._team_repository.get_internal_ids_by_external_ids(
            {player.team_external_fpl_id for player in mapped.players}
        )

        players: list[Player] = []
        for player_seed in mapped.players:
            team_id = team_map.get(player_seed.team_external_fpl_id)
            if team_id is None:
                raise DataMappingError(
                    f"No internal team mapping for external team {player_seed.team_external_fpl_id}"
                )

            players.append(
                Player(
                    id=0,
                    external_fpl_id=player_seed.external_fpl_id,
                    first_name=player_seed.first_name,
                    second_name=player_seed.second_name,
                    web_name=player_seed.web_name,
                    team_id=team_id,
                    position=player_seed.position,
                    current_price=player_seed.current_price,
                    status=player_seed.status,
                )
            )

        self._player_repository.upsert_many(players)
        self._gameweek_repository.upsert_many(mapped.gameweeks)

        fixture_payload = self._provider.fetch_fixtures()
        fixture_seeds = map_fixtures(fixture_payload)

        fixture_team_map = self._team_repository.get_internal_ids_by_external_ids(
            {
                external_id
                for fixture in fixture_seeds
                for external_id in (
                    fixture.home_team_external_fpl_id,
                    fixture.away_team_external_fpl_id,
                )
            }
        )
        fixture_gameweek_map = self._gameweek_repository.get_internal_ids_by_numbers(
            {
                fixture.gameweek_number
                for fixture in fixture_seeds
                if fixture.gameweek_number is not None
            }
        )

        fixtures: list[Fixture] = []
        for fixture_seed in fixture_seeds:
            home_team_id = fixture_team_map.get(fixture_seed.home_team_external_fpl_id)
            away_team_id = fixture_team_map.get(fixture_seed.away_team_external_fpl_id)
            if home_team_id is None or away_team_id is None:
                raise DataMappingError(
                    "Missing team mapping for fixture "
                    f"{fixture_seed.external_fpl_id} "
                    f"(home={fixture_seed.home_team_external_fpl_id}, "
                    f"away={fixture_seed.away_team_external_fpl_id})"
                )

            gameweek_id: int | None = None
            if fixture_seed.gameweek_number is not None:
                gameweek_id = fixture_gameweek_map.get(fixture_seed.gameweek_number)
                if gameweek_id is None:
                    raise DataMappingError(
                        "Missing gameweek mapping for fixture "
                        f"{fixture_seed.external_fpl_id} "
                        f"(event={fixture_seed.gameweek_number})"
                    )

            fixtures.append(
                Fixture(
                    id=0,
                    external_fpl_id=fixture_seed.external_fpl_id,
                    gameweek_id=gameweek_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    kickoff_time=fixture_seed.kickoff_time,
                    home_score=fixture_seed.home_score,
                    away_score=fixture_seed.away_score,
                    finished=fixture_seed.finished,
                )
            )

        self._fixture_repository.upsert_many(fixtures)

        snapshots = self._build_snapshots(payload, fixture_gameweek_map)
        self._player_snapshot_repository.upsert_many(snapshots)

        return ImportSummary(
            teams_imported=len(mapped.teams),
            players_imported=len(players),
            gameweeks_imported=len(mapped.gameweeks),
            fixtures_imported=len(fixtures),
            player_snapshots_captured=len(snapshots),
        )

    def _build_snapshots(
        self, payload: BootstrapStaticDto, gameweek_map: dict[int, int]
    ) -> list[PlayerSnapshot]:
        seeds = map_player_snapshots(payload, captured_at=dt.datetime.now(dt.UTC))
        if not seeds:
            return []

        player_map = self._player_repository.get_internal_ids_by_external_ids(
            {seed.player_external_fpl_id for seed in seeds}
        )

        gameweek_numbers = {
            seed.gameweek_number for seed in seeds if seed.gameweek_number is not None
        }
        missing_numbers = gameweek_numbers - gameweek_map.keys()
        if missing_numbers:
            gameweek_map = {
                **gameweek_map,
                **self._gameweek_repository.get_internal_ids_by_numbers(missing_numbers),
            }

        snapshots: list[PlayerSnapshot] = []
        for seed in seeds:
            player_id = player_map.get(seed.player_external_fpl_id)
            if player_id is None:
                continue

            snapshots.append(
                PlayerSnapshot(
                    player_id=player_id,
                    captured_at=seed.captured_at,
                    gameweek_id=(
                        gameweek_map.get(seed.gameweek_number)
                        if seed.gameweek_number is not None
                        else None
                    ),
                    price=seed.price,
                    ownership_percent=seed.ownership_percent,
                    transfers_in=seed.transfers_in,
                    transfers_out=seed.transfers_out,
                    status=seed.status,
                    chance_of_playing_next_round=seed.chance_of_playing_next_round,
                    total_minutes=seed.total_minutes,
                    total_points=seed.total_points,
                    starts=seed.starts,
                    points_per_game=seed.points_per_game,
                    form=seed.form,
                    expected_goals=seed.expected_goals,
                    expected_assists=seed.expected_assists,
                    expected_goals_per_90=seed.expected_goals_per_90,
                    expected_assists_per_90=seed.expected_assists_per_90,
                    expected_goals_conceded_per_90=seed.expected_goals_conceded_per_90,
                    goals_conceded_per_90=seed.goals_conceded_per_90,
                    clean_sheets_per_90=seed.clean_sheets_per_90,
                    saves_per_90=seed.saves_per_90,
                    starts_per_90=seed.starts_per_90,
                    defensive_contribution_per_90=seed.defensive_contribution_per_90,
                    penalties_order=seed.penalties_order,
                    direct_freekicks_order=seed.direct_freekicks_order,
                    corners_order=seed.corners_order,
                    team_join_date=seed.team_join_date,
                    ep_next=seed.ep_next,
                )
            )

        return snapshots
