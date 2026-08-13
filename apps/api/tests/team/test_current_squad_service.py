from api.repositories.current_squad_repository import CurrentSquadPlayerRecord, CurrentSquadRecord
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.services.current_squad import (
    CurrentSquadPlayerSelection,
    GetCurrentSquadService,
    UpsertCurrentSquadRequest,
    UpsertCurrentSquadService,
)


def _selection(
    player_id: int,
    *,
    is_starting: bool,
    bench_order: int | None,
    is_captain: bool = False,
    is_vice_captain: bool = False,
) -> CurrentSquadPlayerSelection:
    return CurrentSquadPlayerSelection(
        player_id=player_id,
        is_starting=is_starting,
        bench_order=bench_order,
        is_captain=is_captain,
        is_vice_captain=is_vice_captain,
    )


class _FakeCurrentSquadRepository:
    def __init__(self) -> None:
        self.saved_request: tuple[float, int, list[int]] | None = None

    def get_current(self) -> CurrentSquadRecord | None:
        return CurrentSquadRecord(
            squad_id=1,
            name="My Team",
            bank=1.5,
            free_transfers=2,
            players=[
                CurrentSquadPlayerRecord(
                    player_id=1,
                    web_name="Saka",
                    first_name="Bukayo",
                    second_name="Saka",
                    team_name="Arsenal",
                    team_short_name="ARS",
                    position="MID",
                    current_price=10.5,
                    status="a",
                    is_starting=True,
                    bench_order=None,
                    is_captain=True,
                    is_vice_captain=False,
                )
            ],
        )

    def save_current(
        self,
        *,
        bank: float,
        free_transfers: int,
        players: list,
    ) -> CurrentSquadRecord:
        self.saved_request = (bank, free_transfers, [player.player_id for player in players])
        return self.get_current()  # type: ignore[return-value]


class _FakeSquadPlayerLookupRepository:
    def __init__(self, players: list[SquadPlayerLookupItem]) -> None:
        self._players = players

    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]:
        return [player for player in self._players if player.player_id in player_ids]


def _build_valid_request() -> UpsertCurrentSquadRequest:
    players = [
        _selection(1, is_starting=True, bench_order=None, is_captain=True),
        _selection(2, is_starting=True, bench_order=None, is_vice_captain=True),
        _selection(3, is_starting=True, bench_order=None),
        _selection(4, is_starting=True, bench_order=None),
        _selection(5, is_starting=True, bench_order=None),
        _selection(6, is_starting=True, bench_order=None),
        _selection(7, is_starting=True, bench_order=None),
        _selection(8, is_starting=True, bench_order=None),
        _selection(9, is_starting=True, bench_order=None),
        _selection(10, is_starting=True, bench_order=None),
        _selection(11, is_starting=True, bench_order=None),
        _selection(12, is_starting=False, bench_order=1),
        _selection(13, is_starting=False, bench_order=2),
        _selection(14, is_starting=False, bench_order=3),
        _selection(15, is_starting=False, bench_order=4),
    ]

    return UpsertCurrentSquadRequest(bank=1.5, free_transfers=2, players=players)


def _build_lookup_players() -> list[SquadPlayerLookupItem]:
    specs = [
        (1, 1, "GK1", "GK"),
        (2, 2, "GK2", "GK"),
        (3, 1, "DEF1", "DEF"),
        (4, 2, "DEF2", "DEF"),
        (5, 3, "DEF3", "DEF"),
        (6, 4, "DEF4", "DEF"),
        (7, 5, "DEF5", "DEF"),
        (8, 6, "MID1", "MID"),
        (9, 7, "MID2", "MID"),
        (10, 8, "MID3", "MID"),
        (11, 9, "MID4", "MID"),
        (12, 10, "MID5", "MID"),
        (13, 3, "FWD1", "FWD"),
        (14, 4, "FWD2", "FWD"),
        (15, 5, "FWD3", "FWD"),
    ]
    return [
        SquadPlayerLookupItem(
            player_id=player_id,
            team_id=team_id,
            web_name=web_name,
            position=position,
            current_price=5.0,
        )
        for player_id, team_id, web_name, position in specs
    ]


def test_get_current_squad_service_returns_current_squad() -> None:
    service = GetCurrentSquadService(_FakeCurrentSquadRepository())

    result = service.execute()

    assert result is not None
    assert result.name == "My Team"
    assert result.players[0].web_name == "Saka"


def test_upsert_current_squad_service_validates_and_saves() -> None:
    repository = _FakeCurrentSquadRepository()
    service = UpsertCurrentSquadService(
        repository,
        _FakeSquadPlayerLookupRepository(_build_lookup_players()),
    )

    service.execute(_build_valid_request())

    assert repository.saved_request == (1.5, 2, list(range(1, 16)))


def test_upsert_current_squad_service_rejects_duplicate_players() -> None:
    request = _build_valid_request()
    players = list(request.players)
    players[-1] = _selection(1, is_starting=False, bench_order=4)
    invalid_request = UpsertCurrentSquadRequest(
        bank=request.bank,
        free_transfers=request.free_transfers,
        players=players,
    )
    service = UpsertCurrentSquadService(
        _FakeCurrentSquadRepository(),
        _FakeSquadPlayerLookupRepository(_build_lookup_players()),
    )

    try:
        service.execute(invalid_request)
    except ValueError as error:
        assert str(error) == "Squad cannot contain duplicate players"
    else:
        raise AssertionError("Expected ValueError for duplicate players")
