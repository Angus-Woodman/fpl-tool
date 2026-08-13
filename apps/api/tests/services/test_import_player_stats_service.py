from __future__ import annotations

import datetime as dt

import pytest
from api.adapters.fpl.schemas import EventLiveDto
from api.services.import_player_stats import ImportPlayerStatsService
from fpl_engine.domain import Gameweek, PlayerGameweekStat


def _gameweek(number: int, *, finished: bool) -> Gameweek:
    return Gameweek(
        id=200 + number,
        number=number,
        name=f"Gameweek {number}",
        deadline=dt.datetime(2026, 8, 21, 17, 30, tzinfo=dt.UTC),
        is_current=False,
        is_next=False,
        is_finished=finished,
    )


class _FakeProvider:
    def __init__(self, payloads: dict[int, dict[str, object]]) -> None:
        self._payloads = payloads
        self.requested: list[int] = []

    def fetch_event_live(self, event_id: int) -> EventLiveDto:
        self.requested.append(event_id)
        return EventLiveDto.model_validate(self._payloads.get(event_id, {"elements": []}))


class _FakeGameweekRepository:
    def __init__(self, gameweeks: list[Gameweek]) -> None:
        self._gameweeks = gameweeks

    def list_finished(self) -> list[Gameweek]:
        return list(self._gameweeks)

    def get_internal_ids_by_numbers(self, numbers: set[int]) -> dict[int, int]:
        return {
            gameweek.number: gameweek.id
            for gameweek in self._gameweeks
            if gameweek.number in numbers
        }


class _FakePlayerRepository:
    def __init__(self, player_map: dict[int, int]) -> None:
        self._player_map = player_map

    def get_internal_ids_by_external_ids(self, external_ids: set[int]) -> dict[int, int]:
        return {
            external_id: self._player_map[external_id]
            for external_id in external_ids
            if external_id in self._player_map
        }


class _FakeStatRepository:
    def __init__(self) -> None:
        self.stats: list[PlayerGameweekStat] = []
        self.calls = 0

    def upsert_many(self, stats: list[PlayerGameweekStat]) -> None:
        self.calls += 1
        self.stats.extend(stats)


def _payload(player_id: int, *, minutes: int, points: int) -> dict[str, object]:
    return {"elements": [{"id": player_id, "stats": {"minutes": minutes, "total_points": points}}]}


@pytest.fixture
def stat_repository() -> _FakeStatRepository:
    return _FakeStatRepository()


def test_imports_actuals_for_finished_gameweeks(stat_repository: _FakeStatRepository) -> None:
    provider = _FakeProvider({1: _payload(101, minutes=90, points=8)})
    service = ImportPlayerStatsService(
        provider=provider,
        gameweek_repository=_FakeGameweekRepository([_gameweek(1, finished=True)]),
        player_repository=_FakePlayerRepository({101: 501}),
        stat_repository=stat_repository,
    )

    summary = service.import_finished_gameweeks()

    assert provider.requested == [1]
    assert summary.gameweeks_imported == 1
    assert summary.stats_imported == 1
    assert stat_repository.stats[0].player_id == 501
    assert stat_repository.stats[0].gameweek_id == 201
    assert stat_repository.stats[0].minutes == 90
    assert stat_repository.stats[0].fixture_id is None


def test_ignores_unfinished_gameweeks(stat_repository: _FakeStatRepository) -> None:
    provider = _FakeProvider({})
    service = ImportPlayerStatsService(
        provider=provider,
        gameweek_repository=_FakeGameweekRepository([]),
        player_repository=_FakePlayerRepository({101: 501}),
        stat_repository=stat_repository,
    )

    summary = service.import_finished_gameweeks()

    assert provider.requested == []
    assert summary.gameweeks_imported == 0
    assert summary.stats_imported == 0


def test_empty_pre_season_response_is_safe(stat_repository: _FakeStatRepository) -> None:
    provider = _FakeProvider({1: {"elements": []}})
    service = ImportPlayerStatsService(
        provider=provider,
        gameweek_repository=_FakeGameweekRepository([_gameweek(1, finished=True)]),
        player_repository=_FakePlayerRepository({101: 501}),
        stat_repository=stat_repository,
    )

    summary = service.import_finished_gameweeks()

    assert summary.stats_imported == 0
    assert stat_repository.stats == []


def test_unknown_players_are_skipped(stat_repository: _FakeStatRepository) -> None:
    provider = _FakeProvider({1: _payload(999, minutes=90, points=8)})
    service = ImportPlayerStatsService(
        provider=provider,
        gameweek_repository=_FakeGameweekRepository([_gameweek(1, finished=True)]),
        player_repository=_FakePlayerRepository({101: 501}),
        stat_repository=stat_repository,
    )

    summary = service.import_finished_gameweeks()

    assert summary.stats_imported == 0


def test_a_single_gameweek_can_be_imported(stat_repository: _FakeStatRepository) -> None:
    provider = _FakeProvider({4: _payload(101, minutes=45, points=3)})
    service = ImportPlayerStatsService(
        provider=provider,
        gameweek_repository=_FakeGameweekRepository(
            [_gameweek(1, finished=True), _gameweek(4, finished=True)]
        ),
        player_repository=_FakePlayerRepository({101: 501}),
        stat_repository=stat_repository,
    )

    summary = service.import_gameweek(4)

    assert provider.requested == [4]
    assert summary.gameweeks_imported == 1
    assert stat_repository.stats[0].gameweek_id == 204


def test_importing_an_unknown_gameweek_raises(stat_repository: _FakeStatRepository) -> None:
    service = ImportPlayerStatsService(
        provider=_FakeProvider({}),
        gameweek_repository=_FakeGameweekRepository([]),
        player_repository=_FakePlayerRepository({}),
        stat_repository=stat_repository,
    )

    with pytest.raises(LookupError):
        service.import_gameweek(9)
