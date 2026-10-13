from __future__ import annotations

import datetime as dt

import pytest
from api.repositories.current_squad_repository import CurrentSquadPlayerRecord, CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.get_transfer_preview import (
    GetTransferPreviewService,
    TransferPreviewFailure,
)

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


def _candidate(
    player_id: int,
    *,
    team_id: int,
    price: float = 5.0,
    position: str = "MID",
    status: str = "a",
    can_select: bool | None = True,
    can_transact: bool | None = True,
) -> CandidatePlayerRecord:
    return CandidatePlayerRecord(
        player_id=player_id,
        web_name=f"Candidate{player_id}",
        team_id=team_id,
        team_short_name=f"C{team_id}",
        current_price=price,
        position=position,
        status=status,
        can_select=can_select,
        can_transact=can_transact,
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

    def get_current(self) -> CurrentSquadRecord | None:
        return self._squad


class _FakeProjectionRunRepository:
    def __init__(self, run: ProjectionRunRecord | None) -> None:
        self._run = run
        self.calls = 0

    def get_latest(self, model_version: str) -> ProjectionRunRecord | None:
        self.calls += 1
        return self._run


class _FakeProjectionRepository:
    def __init__(self, rows: list[PlayerProjectionFixtureRecord]) -> None:
        self._rows = rows
        self.calls = 0

    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]:
        self.calls += 1
        return [row for row in self._rows if row.player_id in player_ids]


class _FakePlayerRepository:
    def __init__(self, players_by_id: dict[int, CandidatePlayerRecord]) -> None:
        self._players_by_id = players_by_id

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None:
        return self._players_by_id.get(player_id)


def _service(
    *,
    squad: CurrentSquadRecord | None,
    run: ProjectionRunRecord | None,
    rows: list[PlayerProjectionFixtureRecord],
    players_by_id: dict[int, CandidatePlayerRecord],
) -> GetTransferPreviewService:
    return GetTransferPreviewService(
        _FakeCurrentSquadRepository(squad),
        _FakeProjectionRunRepository(run),
        _FakeProjectionRepository(rows),
        _FakePlayerRepository(players_by_id),
    )


def test_returns_none_when_no_squad_is_saved() -> None:
    service = _service(squad=None, run=_run(), rows=[], players_by_id={})

    assert service.execute(PLAYER_OUT_ID, 202) is None


def test_fails_when_the_outgoing_player_is_not_in_the_squad() -> None:
    service = _service(
        squad=_squad(),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55)},
    )

    result = service.execute(999, 202)

    assert isinstance(result, TransferPreviewFailure)
    assert result.code == "player_not_in_squad"


def test_fails_when_the_incoming_player_does_not_exist() -> None:
    service = _service(squad=_squad(), run=_run(), rows=_rows({}), players_by_id={})

    result = service.execute(PLAYER_OUT_ID, 999999)

    assert isinstance(result, TransferPreviewFailure)
    assert result.code == "player_not_found"


def test_fails_when_no_projection_run_exists() -> None:
    service = _service(
        squad=_squad(),
        run=None,
        rows=[],
        players_by_id={202: _candidate(202, team_id=55)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert isinstance(result, TransferPreviewFailure)
    assert result.code == "no_projection_run"


def test_fails_when_a_player_is_missing_a_projection() -> None:
    rows = [row for row in _rows({202: 4.0}) if row.player_id != 10]
    service = _service(
        squad=_squad(),
        run=_run(),
        rows=rows,
        players_by_id={202: _candidate(202, team_id=55)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert isinstance(result, TransferPreviewFailure)
    assert result.code == "missing_projections"
    assert result.missing_player_ids == (10,)


def test_a_legal_preview_reports_lineups_bank_and_gain() -> None:
    service = _service(
        squad=_squad(bank=1.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, price=5.0)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert not isinstance(result, TransferPreviewFailure)
    assert result is not None
    assert result.is_legal is True
    assert result.errors == ()
    assert result.resulting_bank == 1.0
    assert result.lineup_before is not None
    assert result.lineup_after is not None
    assert result.captain_changed is False
    assert result.vice_captain_changed is False
    assert result.direct_player_xpts_difference == 4.0 - 3.3


def test_captain_changes_when_the_incoming_player_projects_highest() -> None:
    service = _service(
        squad=_squad(bank=1.0),
        run=_run(),
        rows=_rows({500: 10.0}),
        players_by_id={500: _candidate(500, team_id=55, price=5.0)},
    )

    result = service.execute(PLAYER_OUT_ID, 500)

    assert not isinstance(result, TransferPreviewFailure)
    assert result is not None
    assert result.lineup_after is not None
    assert result.lineup_after.captain == 500
    assert result.captain_changed is True


def test_an_illegal_preview_is_still_returned_not_raised() -> None:
    # Candidate is unaffordable given bank -- the domain function marks this
    # illegal but the preview still reports it (never a hard error) so the
    # UI can explain why.
    service = _service(
        squad=_squad(bank=0.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, price=999.0)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert not isinstance(result, TransferPreviewFailure)
    assert result is not None
    assert result.is_legal is False
    assert "insufficient_bank" in result.errors


def test_read_only_the_fake_squad_repository_exposes_no_save_method() -> None:
    service = _service(
        squad=_squad(),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55)},
    )

    service.execute(PLAYER_OUT_ID, 202)

    assert not hasattr(service._current_squad_repository, "save_current")  # type: ignore[attr-defined]


def _pool_failure(candidate: CandidatePlayerRecord) -> tuple[TransferPreviewFailure, int, int]:
    service = _service(
        squad=_squad(),
        run=_run(),
        rows=_rows({candidate.player_id: 4.0}),
        players_by_id={candidate.player_id: candidate},
    )

    result = service.execute(PLAYER_OUT_ID, candidate.player_id)

    assert isinstance(result, TransferPreviewFailure)
    run_calls = service._projection_run_repository.calls  # type: ignore[attr-defined]
    projection_calls = service._projection_repository.calls  # type: ignore[attr-defined]
    return result, run_calls, projection_calls


def test_rejects_an_incoming_player_of_a_different_position_before_loading_projections() -> None:
    result, run_calls, projection_calls = _pool_failure(_candidate(202, team_id=55, position="FWD"))

    assert result.code == "player_not_in_candidate_pool"
    assert "different position" in result.message
    assert (run_calls, projection_calls) == (0, 0)


def test_rejects_an_incoming_player_who_is_already_in_the_squad() -> None:
    result, run_calls, projection_calls = _pool_failure(_candidate(10, team_id=10))

    assert result.code == "player_not_in_candidate_pool"
    assert "already in your squad" in result.message
    assert (run_calls, projection_calls) == (0, 0)


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(False, False), (False, True), (True, False)],
)
def test_rejects_a_known_non_selectable_incoming_player(
    can_select: bool, can_transact: bool
) -> None:
    result, run_calls, projection_calls = _pool_failure(
        _candidate(202, team_id=55, can_select=can_select, can_transact=can_transact)
    )

    assert result.code == "player_not_in_candidate_pool"
    assert "not currently selectable" in result.message
    assert (run_calls, projection_calls) == (0, 0)


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(None, None), (True, None), (None, True)],
)
def test_asks_for_a_refresh_when_selectability_is_unknown(
    can_select: bool | None, can_transact: bool | None
) -> None:
    result, run_calls, projection_calls = _pool_failure(
        _candidate(202, team_id=55, can_select=can_select, can_transact=can_transact)
    )

    assert result.code == "player_not_in_candidate_pool"
    assert "refresh" in result.message.lower()
    assert (run_calls, projection_calls) == (0, 0)


def test_a_known_false_flag_beside_an_unknown_one_is_reported_as_not_selectable() -> None:
    result, *_ = _pool_failure(_candidate(202, team_id=55, can_select=False, can_transact=None))

    assert "not currently selectable" in result.message
    assert "refresh" not in result.message.lower()


def test_structural_exclusions_outrank_unknown_selectability() -> None:
    owned, *_ = _pool_failure(_candidate(10, team_id=10, can_select=None, can_transact=None))
    other_position, *_ = _pool_failure(
        _candidate(202, team_id=55, position="FWD", can_select=None, can_transact=None)
    )

    assert "already in your squad" in owned.message
    assert "different position" in other_position.message
    assert "refresh" not in owned.message.lower()
    assert "refresh" not in other_position.message.lower()


@pytest.mark.parametrize("status", ["i", "d", "s"])
def test_previews_an_unavailable_playing_status_player_when_both_flags_are_true(
    status: str,
) -> None:
    service = _service(
        squad=_squad(bank=1.0),
        run=_run(),
        rows=_rows({202: 4.0}),
        players_by_id={202: _candidate(202, team_id=55, status=status)},
    )

    result = service.execute(PLAYER_OUT_ID, 202)

    assert not isinstance(result, TransferPreviewFailure)
    assert result is not None
    assert result.is_legal is True
