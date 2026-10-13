from __future__ import annotations

import datetime as dt

from api.repositories.current_squad_repository import (
    CurrentSquadPlayerRecord,
    CurrentSquadRecord,
)
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.apply_transfer import ApplyTransferFailure, ApplyTransferService
from api.services.get_my_team_view import MyTeamViewRecord

RUN_GENERATED_AT = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC)
PLAYER_OUT_ID = 9


def _player(
    player_id: int,
    position: str,
    *,
    is_starting: bool,
    bench_order: int | None = None,
    is_captain: bool = False,
    is_vice_captain: bool = False,
    team_id: int | None = None,
) -> CurrentSquadPlayerRecord:
    return CurrentSquadPlayerRecord(
        player_id=player_id,
        web_name=f"Player{player_id}",
        first_name="First",
        second_name=f"Player{player_id}",
        team_name=f"Team{player_id}",
        team_short_name=f"T{player_id}",
        position=position,
        current_price=5.0,
        status="a",
        is_starting=is_starting,
        bench_order=bench_order,
        is_captain=is_captain,
        is_vice_captain=is_vice_captain,
        team_id=team_id if team_id is not None else player_id,
    )


def _squad(bank: float = 1.0) -> CurrentSquadRecord:
    return CurrentSquadRecord(
        squad_id=1,
        name="My Team",
        bank=bank,
        free_transfers=1,
        players=[
            _player(1, "GK", is_starting=True),
            _player(2, "GK", is_starting=False, bench_order=1),
            _player(3, "DEF", is_starting=True),
            _player(4, "DEF", is_starting=True),
            _player(5, "DEF", is_starting=True),
            _player(6, "DEF", is_starting=False, bench_order=2),
            _player(7, "DEF", is_starting=False, bench_order=3),
            _player(8, "MID", is_starting=True, is_captain=True),
            _player(PLAYER_OUT_ID, "MID", is_starting=True),
            _player(10, "MID", is_starting=True),
            _player(11, "MID", is_starting=False, bench_order=4),
            _player(12, "MID", is_starting=True),
            _player(13, "FWD", is_starting=True, is_vice_captain=True),
            _player(14, "FWD", is_starting=True),
            _player(15, "FWD", is_starting=True),
        ],
    )


def _candidate(player_id: int, *, team_id: int, price: float = 5.0) -> CandidatePlayerRecord:
    return CandidatePlayerRecord(
        player_id=player_id,
        web_name=f"Candidate{player_id}",
        team_id=team_id,
        team_short_name=f"C{team_id}",
        current_price=price,
        position="MID",
        status="a",
        can_select=True,
        can_transact=True,
    )


def _run(run_id: int = 1) -> ProjectionRunRecord:
    return ProjectionRunRecord(
        id=run_id,
        model_version="component_v3",
        generated_at=RUN_GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot={},
        player_snapshot_generated_at=RUN_GENERATED_AT,
    )


_SQUAD_POINTS_GW5 = {
    1: 3.6,
    2: 2.0,
    3: 3.0,
    4: 2.8,
    5: 2.5,
    6: 1.0,
    7: 0.5,
    8: 3.5,
    9: 3.3,
    10: 2.9,
    11: 0.2,
    12: 0.1,
    13: 4.5,
    14: 4.0,
    15: 3.8,
}


def _rows(extra_points: dict[int, float]) -> list[PlayerProjectionFixtureRecord]:
    points = {**_SQUAD_POINTS_GW5, **extra_points}
    return [
        PlayerProjectionFixtureRecord(
            player_id=player_id,
            fixture_id=1000 + player_id,
            gameweek_number=5,
            projected_points=value,
            kickoff_time="2026-09-20T15:00:00+00:00",
            opponent_team_short_name="CHE",
            is_home=True,
        )
        for player_id, value in points.items()
    ]


class _FakeCurrentSquadRepository:
    def __init__(self, squad: CurrentSquadRecord | None) -> None:
        self._squad = squad
        self.saved_players = None
        self.saved_bank: float | None = None
        self.save_calls = 0

    def get_current(self) -> CurrentSquadRecord | None:
        return self._squad

    def save_current(self, *, bank, free_transfers, players):  # type: ignore[no-untyped-def]
        self.save_calls += 1
        self.saved_bank = bank
        self.saved_players = players
        updated = [
            _player(
                player.player_id,
                "MID",
                is_starting=player.is_starting,
                bench_order=player.bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
            )
            for player in players
        ]
        self._squad = CurrentSquadRecord(
            squad_id=1, name="My Team", bank=bank, free_transfers=free_transfers, players=updated
        )
        return self._squad


class _FakeProjectionRunRepository:
    def __init__(self, run: ProjectionRunRecord | None) -> None:
        self._run = run

    def get_latest(self, model_version: str) -> ProjectionRunRecord | None:
        return self._run


class _FakeProjectionRepository:
    def __init__(self, rows: list[PlayerProjectionFixtureRecord]) -> None:
        self._rows = rows

    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]:
        return [row for row in self._rows if row.player_id in player_ids]


class _FakePlayerRepository:
    def __init__(self, players_by_id: dict[int, CandidatePlayerRecord]) -> None:
        self._players_by_id = players_by_id

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None:
        return self._players_by_id.get(player_id)


class _FakeMyTeamViewService:
    def __init__(self) -> None:
        self.call_count = 0

    def execute(self) -> MyTeamViewRecord | None:
        self.call_count += 1
        return MyTeamViewRecord(
            squad_id=1,
            name="My Team",
            bank=1.0,
            free_transfers=1,
            players=[],
            projection_totals=None,
            bench_projection_totals=None,
            captain_adjusted_projection_totals=None,
            gameweek_numbers=[5],
        )


def _service(
    *,
    squad: CurrentSquadRecord | None,
    run: ProjectionRunRecord | None,
    rows: list[PlayerProjectionFixtureRecord],
    players_by_id: dict[int, CandidatePlayerRecord],
) -> tuple[ApplyTransferService, _FakeCurrentSquadRepository, _FakeMyTeamViewService]:
    squad_repository = _FakeCurrentSquadRepository(squad)
    view_service = _FakeMyTeamViewService()
    service = ApplyTransferService(
        squad_repository,
        _FakeProjectionRunRepository(run),
        _FakeProjectionRepository(rows),
        _FakePlayerRepository(players_by_id),
        view_service,
    )
    return service, squad_repository, view_service


def test_returns_none_when_no_squad_is_saved() -> None:
    service, *_ = _service(squad=None, run=_run(), rows=[], players_by_id={})

    assert service.execute(PLAYER_OUT_ID, 202) is None


def test_fails_when_the_outgoing_player_is_not_in_the_squad() -> None:
    service, *_ = _service(
        squad=_squad(),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55)},
    )

    result = service.execute(999, 202)

    assert isinstance(result, ApplyTransferFailure)
    assert result.code == "player_not_in_squad"


def test_fails_when_the_incoming_player_does_not_exist() -> None:
    service, *_ = _service(squad=_squad(), run=_run(), rows=_rows({}), players_by_id={})

    result = service.execute(PLAYER_OUT_ID, 999999)

    assert isinstance(result, ApplyTransferFailure)
    assert result.code == "player_not_found"


def test_fails_when_no_projection_run_exists() -> None:
    service, *_ = _service(
        squad=_squad(),
        run=None,
        rows=[],
        players_by_id={202: _candidate(202, team_id=55)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert isinstance(result, ApplyTransferFailure)
    assert result.code == "no_projection_run"


def test_fails_when_a_player_is_missing_a_projection() -> None:
    rows = [row for row in _rows({202: 4.0}) if row.player_id != 10]
    service, *_ = _service(
        squad=_squad(),
        run=_run(),
        rows=rows,
        players_by_id={202: _candidate(202, team_id=55)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert isinstance(result, ApplyTransferFailure)
    assert result.code == "missing_projections"
    assert result.missing_player_ids == (10,)


def test_rejects_an_illegal_transfer_without_persisting() -> None:
    service, squad_repository, _ = _service(
        squad=_squad(bank=0.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, price=999.0)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert isinstance(result, ApplyTransferFailure)
    assert result.code == "transfer_illegal"
    assert "insufficient_bank" in result.errors
    assert squad_repository.save_calls == 0


def test_applies_a_legal_transfer_replacing_exactly_the_outgoing_player() -> None:
    service, squad_repository, view_service = _service(
        squad=_squad(bank=1.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, price=5.0)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert not isinstance(result, ApplyTransferFailure)
    assert result is not None
    assert squad_repository.save_calls == 1
    assert squad_repository.saved_bank == 1.0
    saved_ids = {player.player_id for player in squad_repository.saved_players}
    assert PLAYER_OUT_ID not in saved_ids
    assert 202 in saved_ids
    assert len(saved_ids) == 15
    assert view_service.call_count == 1


def test_the_incoming_player_takes_over_the_outgoing_players_exact_slot() -> None:
    service, squad_repository, _ = _service(
        squad=_squad(bank=1.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, price=5.0)},
    )

    service.execute(PLAYER_OUT_ID, 202)

    incoming_save = next(p for p in squad_repository.saved_players if p.player_id == 202)
    assert incoming_save.is_starting is True
    assert incoming_save.bench_order is None
    assert incoming_save.is_captain is False
    assert incoming_save.is_vice_captain is False


def test_free_transfers_are_left_unchanged() -> None:
    service, squad_repository, _ = _service(
        squad=_squad(bank=1.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, price=5.0)},
    )

    service.execute(PLAYER_OUT_ID, 202)

    saved_squad = squad_repository.get_current()
    assert saved_squad is not None
    assert saved_squad.free_transfers == 1
