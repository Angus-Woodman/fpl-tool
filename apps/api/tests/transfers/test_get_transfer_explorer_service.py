from __future__ import annotations

import datetime as dt

from api.repositories.current_squad_repository import CurrentSquadPlayerRecord, CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.get_transfer_explorer import (
    GetTransferExplorerService,
    TransferExplorerFailure,
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
    current_price: float = 5.0,
) -> CurrentSquadPlayerRecord:
    return CurrentSquadPlayerRecord(
        player_id=player_id,
        web_name=f"Player{player_id}",
        first_name="First",
        second_name=f"Player{player_id}",
        team_name=f"Team{team_id if team_id is not None else player_id}",
        team_short_name=f"T{team_id if team_id is not None else player_id}",
        position=position,
        current_price=current_price,
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
            # Three DEF players share team_id=100 -- used to prove the
            # club-limit check excludes a same-club replacement candidate.
            _player(3, "DEF", is_starting=True, team_id=100),
            _player(4, "DEF", is_starting=True, team_id=100),
            _player(5, "DEF", is_starting=True, team_id=100),
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
    position: str = "MID",
    *,
    team_id: int,
    price: float = 5.0,
) -> CandidatePlayerRecord:
    return CandidatePlayerRecord(
        player_id=player_id,
        web_name=f"Candidate{player_id}",
        team_id=team_id,
        team_short_name=f"C{team_id}",
        current_price=price,
        position=position,
        status="a",
        can_select=True,
        can_transact=True,
    )


def _run(run_id: int = 1, model_version: str = "component_v3") -> ProjectionRunRecord:
    return ProjectionRunRecord(
        id=run_id,
        model_version=model_version,
        generated_at=RUN_GENERATED_AT,
        gameweeks_covered=[5, 6, 7],
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
_CANDIDATE_POINTS_GW5 = {201: 3.0, 202: 4.0, 203: 2.0, 204: 2.5}


def _rows_for_gameweek(
    gameweek_number: int, points: dict[int, float]
) -> list[PlayerProjectionFixtureRecord]:
    return [
        PlayerProjectionFixtureRecord(
            player_id=player_id,
            fixture_id=1000 + player_id,
            gameweek_number=gameweek_number,
            projected_points=value,
            kickoff_time="2026-09-20T15:00:00+00:00",
            opponent_team_short_name="CHE",
            is_home=True,
        )
        for player_id, value in points.items()
    ]


def _all_rows() -> list[PlayerProjectionFixtureRecord]:
    all_points = {**_SQUAD_POINTS_GW5, **_CANDIDATE_POINTS_GW5}
    return (
        _rows_for_gameweek(5, all_points)
        + _rows_for_gameweek(6, all_points)
        + _rows_for_gameweek(7, all_points)
    )


class _FakeCurrentSquadRepository:
    def __init__(self, squad: CurrentSquadRecord | None) -> None:
        self._squad = squad

    def get_current(self) -> CurrentSquadRecord | None:
        return self._squad


class _FakeProjectionRunRepository:
    def __init__(self, runs_by_model: dict[str, ProjectionRunRecord | None]) -> None:
        self._runs_by_model = runs_by_model
        self.requested_model_versions: list[str] = []

    def get_latest(self, model_version: str) -> ProjectionRunRecord | None:
        self.requested_model_versions.append(model_version)
        return self._runs_by_model.get(model_version)


class _FakeProjectionRepository:
    def __init__(self, rows_by_run: dict[int, list[PlayerProjectionFixtureRecord]]) -> None:
        self._rows_by_run = rows_by_run
        self.requested_run_ids: list[int] = []

    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]:
        self.requested_run_ids.append(run_id)
        return [row for row in self._rows_by_run.get(run_id, []) if row.player_id in player_ids]


class _FakePlayerRepository:
    def __init__(
        self,
        candidates: list[CandidatePlayerRecord],
        players_by_id: dict[int, CandidatePlayerRecord] | None = None,
    ) -> None:
        self._candidates = candidates
        self._players_by_id = players_by_id or {}
        self.requested_positions: list[str] = []

    def list_available_by_position(self, position: str) -> list[CandidatePlayerRecord]:
        self.requested_positions.append(position)
        return self._candidates

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None:
        return self._players_by_id.get(player_id)


def _default_candidates() -> list[CandidatePlayerRecord]:
    return [
        _candidate(201, team_id=100, price=5.0),  # same club as 3/4/5 -> club limit
        _candidate(202, team_id=55, price=5.0),  # legal, affordable
        _candidate(203, team_id=55, price=999.0),  # unaffordable
        _candidate(8, team_id=8, price=5.0),  # already owned
        _candidate(204, position="DEF", team_id=77, price=5.0),  # wrong position
    ]


_UNSET = object()


def _service(
    *,
    squad: CurrentSquadRecord | None | object = _UNSET,
    run: ProjectionRunRecord | None | object = _UNSET,
    rows_by_run: dict[int, list[PlayerProjectionFixtureRecord]] | None = None,
    candidates: list[CandidatePlayerRecord] | None = None,
    players_by_id: dict[int, CandidatePlayerRecord] | None = None,
) -> tuple[
    GetTransferExplorerService,
    _FakeProjectionRunRepository,
    _FakeProjectionRepository,
    _FakePlayerRepository,
]:
    resolved_squad = _squad() if squad is _UNSET else squad
    resolved_run = _run() if run is _UNSET else run
    rows_by_run = rows_by_run if rows_by_run is not None else {1: _all_rows()}
    candidates = candidates if candidates is not None else _default_candidates()

    run_repository = _FakeProjectionRunRepository({"component_v3": resolved_run})
    projection_repository = _FakeProjectionRepository(rows_by_run)
    player_repository = _FakePlayerRepository(candidates, players_by_id)
    service = GetTransferExplorerService(
        _FakeCurrentSquadRepository(resolved_squad),
        run_repository,
        projection_repository,
        player_repository,
    )
    return service, run_repository, projection_repository, player_repository


class TestNoSquad:
    def test_returns_none_when_no_squad_is_saved(self) -> None:
        service, *_ = _service(squad=None)

        assert service.execute(PLAYER_OUT_ID) is None


class TestOutgoingPlayerValidation:
    def test_fails_explicitly_when_the_player_is_not_in_the_squad(self) -> None:
        service, _, _, player_repository = _service(
            players_by_id={999: _candidate(999, team_id=999)}
        )

        result = service.execute(999)

        assert isinstance(result, TransferExplorerFailure)
        assert result.code == "player_not_in_squad"

    def test_fails_explicitly_when_no_such_player_exists_at_all(self) -> None:
        service, *_ = _service()

        result = service.execute(999999)

        assert isinstance(result, TransferExplorerFailure)
        assert result.code == "player_not_found"


class TestProjectionRunSelection:
    def test_no_run_for_the_model_is_an_explicit_failure(self) -> None:
        service, run_repository, _, _ = _service(run=None, rows_by_run={})

        result = service.execute(PLAYER_OUT_ID)

        assert isinstance(result, TransferExplorerFailure)
        assert result.code == "no_projection_run"
        assert run_repository.requested_model_versions == ["component_v3"]

    def test_response_uses_the_resolved_runs_identity(self) -> None:
        run = _run(run_id=42)
        service, _, projection_repository, _ = _service(run=run, rows_by_run={42: _all_rows()})

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert result.projection_run_id == 42
        assert result.model_version == "component_v3"
        assert result.generated_at == RUN_GENERATED_AT
        assert projection_repository.requested_run_ids == [42]

    def test_missing_projections_in_the_run_is_an_explicit_failure(self) -> None:
        service, *_ = _service(rows_by_run={1: []})

        result = service.execute(PLAYER_OUT_ID)

        assert isinstance(result, TransferExplorerFailure)
        assert result.code == "missing_projections"

    def test_a_squad_player_missing_from_every_evaluated_gameweek_is_an_explicit_failure(
        self,
    ) -> None:
        rows = [row for row in _all_rows() if row.player_id != 10]
        service, *_ = _service(rows_by_run={1: rows})

        result = service.execute(PLAYER_OUT_ID)

        assert isinstance(result, TransferExplorerFailure)
        assert result.code == "missing_projections"
        assert result.missing_player_ids == (10,)


class TestCandidateFiltering:
    def test_only_same_position_legal_replacements_are_returned(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        returned_ids = {candidate.player_id for candidate in result.candidates}
        # 201 excluded (club limit), 203 excluded (unaffordable), 8 excluded
        # (already owned), 204 excluded (wrong position).
        assert returned_ids == {202}

    def test_requests_candidates_for_the_outgoing_players_position(self) -> None:
        service, _, _, player_repository = _service()

        service.execute(PLAYER_OUT_ID)

        assert player_repository.requested_positions == ["MID"]

    def test_excludes_a_candidate_that_would_exceed_the_per_club_limit(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert 201 not in {candidate.player_id for candidate in result.candidates}

    def test_excludes_an_unaffordable_candidate(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert 203 not in {candidate.player_id for candidate in result.candidates}

    def test_excludes_an_already_owned_candidate(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert 8 not in {candidate.player_id for candidate in result.candidates}


class TestAggregationAndReporting:
    def test_reports_1_3_5_gw_team_gain_and_resulting_bank(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        candidate = next(c for c in result.candidates if c.player_id == 202)
        assert set(candidate.team_gain_by_horizon) == {1, 3, 5}
        assert candidate.resulting_bank == 1.0  # bank(1.0) + outgoing(5.0) - incoming(5.0)
        assert candidate.gameweeks_evaluated == 3

    def test_caps_a_longer_horizon_to_the_gameweeks_actually_available(self) -> None:
        # Only 3 gameweeks of projections exist; horizon 5 must be honestly
        # capped rather than pretending 5 full gameweeks were evaluated.
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID, primary_horizon=5)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        candidate = next(c for c in result.candidates if c.player_id == 202)
        assert candidate.gameweeks_evaluated == 3
        assert candidate.team_gain_by_horizon[5] == candidate.team_gain_by_horizon[3]

    def test_outgoing_player_summary_includes_position_price_and_horizon_totals(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert result.outgoing.player_id == PLAYER_OUT_ID
        assert result.outgoing.position == "MID"
        assert result.outgoing.current_price == 5.0
        assert result.outgoing.selling_price == 5.0
        assert set(result.outgoing.projected_points_by_horizon) == {1, 3, 5}
        assert result.outgoing.projected_points_by_horizon[1] == 3.3

    def test_selling_price_is_flagged_as_approximate(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert result.selling_price_is_approximate is True

    def test_direct_xpts_difference_uses_the_nearest_gameweek_only(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        candidate = next(c for c in result.candidates if c.player_id == 202)
        # candidate 202 projects 4.0 in GW5, outgoing (9) projects 3.3.
        assert candidate.direct_xpts_difference == 4.0 - 3.3

    def test_ranking_default_horizon_is_5(self) -> None:
        service, *_ = _service()

        result = service.execute(PLAYER_OUT_ID)

        assert not isinstance(result, TransferExplorerFailure)
        assert result is not None
        assert result.primary_horizon == 5
