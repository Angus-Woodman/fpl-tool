import pytest
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
    # Starters 1-11 form a legal 1-4-4-2; the bench (12-15) holds one of each position.
    specs = [
        (1, 1, "GK1", "GK"),
        (2, 2, "DEF1", "DEF"),
        (3, 1, "DEF2", "DEF"),
        (4, 2, "DEF3", "DEF"),
        (5, 3, "DEF4", "DEF"),
        (6, 4, "MID1", "MID"),
        (7, 5, "MID2", "MID"),
        (8, 6, "MID3", "MID"),
        (9, 7, "MID4", "MID"),
        (10, 8, "FWD1", "FWD"),
        (11, 9, "FWD2", "FWD"),
        (12, 10, "GK2", "GK"),
        (13, 3, "DEF5", "DEF"),
        (14, 4, "MID5", "MID"),
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


def _request_with_starters(starter_ids: set[int]) -> UpsertCurrentSquadRequest:
    """Same 15 players; `starter_ids` start and the rest take bench orders 1-4 in id order."""
    base = _build_valid_request()
    bench_order = 0
    players: list[CurrentSquadPlayerSelection] = []
    for player in base.players:
        is_starting = player.player_id in starter_ids
        if not is_starting:
            bench_order += 1
        players.append(
            _selection(
                player.player_id,
                is_starting=is_starting,
                bench_order=None if is_starting else bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
            )
        )
    return UpsertCurrentSquadRequest(
        bank=base.bank, free_transfers=base.free_transfers, players=players
    )


def _service_with_repository() -> tuple[UpsertCurrentSquadService, _FakeCurrentSquadRepository]:
    repository = _FakeCurrentSquadRepository()
    service = UpsertCurrentSquadService(
        repository, _FakeSquadPlayerLookupRepository(_build_lookup_players())
    )
    return service, repository


def test_upsert_current_squad_service_rejects_an_illegal_starting_formation() -> None:
    # Player 12 is a goalkeeper: starting both keepers is a legal 15-player squad
    # but an illegal XI, which only the domain formation rule catches.
    service, repository = _service_with_repository()
    request = _request_with_starters({1, 12, 3, 4, 5, 6, 7, 8, 9, 10, 11})

    with pytest.raises(ValueError, match="Starting XI must contain between 1 and 1 GK"):
        service.execute(request)

    assert repository.saved_request is None


def test_upsert_current_squad_service_accepts_a_five_two_three_formation() -> None:
    # 1 GK, 5 DEF (2-5, 13), 2 MID (6, 7), 3 FWD (10, 11, 15): legal, but a MID >= 3 rule blocks it.
    service, repository = _service_with_repository()
    request = _request_with_starters({1, 2, 3, 4, 5, 13, 6, 7, 10, 11, 15})

    service.execute(request)

    assert repository.saved_request == (1.5, 2, list(range(1, 16)))


def test_upsert_current_squad_service_rejects_wrong_squad_composition() -> None:
    lookup = _build_lookup_players()
    lookup[13] = SquadPlayerLookupItem(
        player_id=14, team_id=4, web_name="DEF6", position="DEF", current_price=5.0
    )
    service = UpsertCurrentSquadService(
        _FakeCurrentSquadRepository(), _FakeSquadPlayerLookupRepository(lookup)
    )

    with pytest.raises(ValueError, match="Squad must contain 2 GK, 5 DEF, 5 MID, and 3 FWD"):
        service.execute(_build_valid_request())


def test_upsert_current_squad_service_rejects_more_than_three_players_per_club() -> None:
    lookup = [
        SquadPlayerLookupItem(
            player_id=item.player_id,
            team_id=1 if item.player_id in {1, 2, 3, 4} else item.team_id,
            web_name=item.web_name,
            position=item.position,
            current_price=item.current_price,
        )
        for item in _build_lookup_players()
    ]
    service = UpsertCurrentSquadService(
        _FakeCurrentSquadRepository(), _FakeSquadPlayerLookupRepository(lookup)
    )

    with pytest.raises(ValueError, match="more than 3 players from one team"):
        service.execute(_build_valid_request())


def test_upsert_current_squad_service_rejects_unknown_players() -> None:
    lookup = _build_lookup_players()[:-1]
    service = UpsertCurrentSquadService(
        _FakeCurrentSquadRepository(), _FakeSquadPlayerLookupRepository(lookup)
    )

    with pytest.raises(ValueError, match="Squad contains unknown players"):
        service.execute(_build_valid_request())


def test_upsert_current_squad_service_rejects_a_bad_captain_or_bench_order() -> None:
    service, _ = _service_with_repository()
    request = _build_valid_request()
    no_captain = UpsertCurrentSquadRequest(
        bank=request.bank,
        free_transfers=request.free_transfers,
        players=[
            _selection(
                p.player_id,
                is_starting=p.is_starting,
                bench_order=p.bench_order,
                is_captain=False,
                is_vice_captain=p.is_vice_captain,
            )
            for p in request.players
        ],
    )
    with pytest.raises(ValueError, match="exactly one captain"):
        service.execute(no_captain)

    bad_bench = UpsertCurrentSquadRequest(
        bank=request.bank,
        free_transfers=request.free_transfers,
        players=[
            _selection(
                p.player_id,
                is_starting=p.is_starting,
                bench_order=1 if not p.is_starting else None,
                is_captain=p.is_captain,
                is_vice_captain=p.is_vice_captain,
            )
            for p in request.players
        ],
    )
    with pytest.raises(ValueError, match="bench order 1, 2, 3, and 4"):
        service.execute(bad_bench)


@pytest.mark.parametrize("bank", [0.5000000000000062, 0.4999999999999938, 0.5000000000000009, 0.5])
def test_upsert_current_squad_service_normalises_bank_representation_noise(
    bank: float,
) -> None:
    # A rearrangement echoes the loaded bank back, so a drifted stored value must be accepted
    # and saved as the exact tenth.
    service, repository = _service_with_repository()
    base = _build_valid_request()
    request = UpsertCurrentSquadRequest(
        bank=bank, free_transfers=base.free_transfers, players=base.players
    )

    service.execute(request)

    assert repository.saved_request is not None
    saved_bank = repository.saved_request[0]
    assert saved_bank == 0.5
    assert repr(saved_bank) == "0.5"


@pytest.mark.parametrize("bank", [0.55, 0.05, 1.234, float("nan"), float("inf"), 1e308])
def test_upsert_current_squad_service_rejects_an_invalid_bank_without_rounding(
    bank: float,
) -> None:
    from fpl_engine.rules import RuleViolationError

    service, repository = _service_with_repository()
    base = _build_valid_request()
    request = UpsertCurrentSquadRequest(
        bank=bank, free_transfers=base.free_transfers, players=base.players
    )

    with pytest.raises(RuleViolationError) as error:
        service.execute(request)

    assert error.value.code == "invalid_money"
    assert error.value.message.startswith("Bank ")
    assert repository.saved_request is None
