from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import Gameweek, PlayerGameweekStat

from api.adapters.fpl.mappers import map_event_live_stats
from api.adapters.fpl.schemas import EventLiveDto


class EventLiveProvider(Protocol):
    def fetch_event_live(self, event_id: int) -> EventLiveDto: ...


class GameweekReadPort(Protocol):
    def list_finished(self) -> list[Gameweek]: ...

    def get_internal_ids_by_numbers(self, numbers: set[int]) -> dict[int, int]: ...


class PlayerLookupPort(Protocol):
    def get_internal_ids_by_external_ids(self, external_ids: set[int]) -> dict[int, int]: ...


class PlayerGameweekStatRepositoryPort(Protocol):
    def upsert_many(self, stats: list[PlayerGameweekStat]) -> None: ...


@dataclass(frozen=True)
class ImportPlayerStatsSummary:
    gameweeks_imported: int
    stats_imported: int


class ImportPlayerStatsService:
    """Import gameweek-aggregated player actuals from /event/{id}/live/.

    UNVERIFIED CONTRACT: the endpoint returns an empty element list until a
    gameweek has been played, so the stat field names are taken from the
    documented shape rather than a captured response. Validate against a real
    payload once GW1 completes, including the `explain` array we do not consume.
    """

    def __init__(
        self,
        provider: EventLiveProvider,
        gameweek_repository: GameweekReadPort,
        player_repository: PlayerLookupPort,
        stat_repository: PlayerGameweekStatRepositoryPort,
    ) -> None:
        self._provider = provider
        self._gameweek_repository = gameweek_repository
        self._player_repository = player_repository
        self._stat_repository = stat_repository

    def import_finished_gameweeks(self) -> ImportPlayerStatsSummary:
        finished = self._gameweek_repository.list_finished()
        return self._import([gameweek.number for gameweek in finished])

    def import_gameweek(self, gameweek_number: int) -> ImportPlayerStatsSummary:
        known = {gameweek.number for gameweek in self._gameweek_repository.list_finished()}
        if gameweek_number not in known:
            raise LookupError(f"Gameweek {gameweek_number} has not finished or does not exist")

        return self._import([gameweek_number])

    def _import(self, gameweek_numbers: list[int]) -> ImportPlayerStatsSummary:
        if not gameweek_numbers:
            return ImportPlayerStatsSummary(gameweeks_imported=0, stats_imported=0)

        gameweek_map = self._gameweek_repository.get_internal_ids_by_numbers(set(gameweek_numbers))

        imported = 0
        for gameweek_number in sorted(gameweek_numbers):
            gameweek_id = gameweek_map.get(gameweek_number)
            if gameweek_id is None:
                continue

            payload = self._provider.fetch_event_live(gameweek_number)
            seeds = map_event_live_stats(payload, gameweek_number=gameweek_number)
            if not seeds:
                continue

            player_map = self._player_repository.get_internal_ids_by_external_ids(
                {seed.player_external_fpl_id for seed in seeds}
            )

            stats = [
                PlayerGameweekStat(
                    player_id=player_map[seed.player_external_fpl_id],
                    gameweek_id=gameweek_id,
                    minutes=seed.minutes,
                    total_points=seed.total_points,
                    goals_scored=seed.goals_scored,
                    assists=seed.assists,
                    clean_sheets=seed.clean_sheets,
                    goals_conceded=seed.goals_conceded,
                    bonus=seed.bonus,
                    bps=seed.bps,
                )
                for seed in seeds
                if seed.player_external_fpl_id in player_map
            ]

            if stats:
                self._stat_repository.upsert_many(stats)
            imported += len(stats)

        return ImportPlayerStatsSummary(
            gameweeks_imported=len(gameweek_numbers), stats_imported=imported
        )
