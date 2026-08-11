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
    return [
        SquadPlayerLookupItem(player_id=1, team_id=1, web_name="GK1", position="GK"),
        SquadPlayerLookupItem(player_id=2, team_id=2, web_name="GK2", position="GK"),
        SquadPlayerLookupItem(player_id=3, team_id=1, web_name="DEF1", position="DEF"),
        SquadPlayerLookupItem(player_id=4, team_id=2, web_name="DEF2", position="DEF"),
        SquadPlayerLookupItem(player_id=5, team_id=3, web_name="DEF3", position="DEF"),
        SquadPlayerLookupItem(player_id=6, team_id=4, web_name="DEF4", position="DEF"),
        SquadPlayerLookupItem(player_id=7, team_id=5, web_name="DEF5", position="DEF"),
        SquadPlayerLookupItem(player_id=8, team_id=6, web_name="MID1", position="MID"),
        SquadPlayerLookupItem(player_id=9, team_id=7, web_name="MID2", position="MID"),
        SquadPlayerLookupItem(player_id=10, team_id=8, web_name="MID3", position="MID"),
        SquadPlayerLookupItem(player_id=11, team_id=9, web_name="MID4", position="MID"),
        SquadPlayerLookupItem(player_id=12, team_id=10, web_name="MID5", position="MID"),
        SquadPlayerLookupItem(player_id=13, team_id=3, web_name="FWD1", position="FWD"),
        SquadPlayerLookupItem(player_id=14, team_id=4, web_name="FWD2", position="FWD"),
        SquadPlayerLookupItem(player_id=15, team_id=5, web_name="FWD3", position="FWD"),
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
