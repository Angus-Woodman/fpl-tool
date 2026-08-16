from __future__ import annotations

import datetime as dt

from api.repositories.current_squad_repository import CurrentSquadPlayerRecord, CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.get_my_team_recommendation import (
    GetMyTeamRecommendationService,
    MyTeamRecommendationFailure,
)

RUN_GENERATED_AT = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC)


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


def _squad() -> CurrentSquadRecord:
    # Position/starting flags here are the CURRENTLY saved selection -- the
    # recommendation is computed independently from projected points, not
    # from these flags, so they're deliberately not "optimal" already.
    return CurrentSquadRecord(
        squad_id=1,
        name="My Team",
        bank=1.0,
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
            _player(9, "MID", is_starting=True),
            _player(10, "MID", is_starting=True),
            _player(11, "MID", is_starting=False, bench_order=4),
            _player(12, "MID", is_starting=True),
            _player(13, "FWD", is_starting=True, is_vice_captain=True),
            _player(14, "FWD", is_starting=True),
            _player(15, "FWD", is_starting=True),
        ],
    )


def _points_for_gameweek(gameweek_number: int) -> dict[int, float]:
    return {
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


class _FakeMyTeamProjectionRepository:
    def __init__(self, rows_by_run: dict[int, list[PlayerProjectionFixtureRecord]]) -> None:
        self._rows_by_run = rows_by_run
        self.requested_run_ids: list[int] = []

    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]:
        self.requested_run_ids.append(run_id)
        return [row for row in self._rows_by_run.get(run_id, []) if row.player_id in player_ids]


def _run(run_id: int, model_version: str = "component_v3") -> ProjectionRunRecord:
    return ProjectionRunRecord(
        id=run_id,
        model_version=model_version,
        generated_at=RUN_GENERATED_AT,
        gameweeks_covered=[5],
        parameters={},
        team_strength_snapshot={},
        player_snapshot_generated_at=RUN_GENERATED_AT,
    )


def _rows_for_run(run_id: int, gameweek_number: int = 5) -> list[PlayerProjectionFixtureRecord]:
    return [
        PlayerProjectionFixtureRecord(
            player_id=player_id,
            fixture_id=100 + player_id,
            gameweek_number=gameweek_number,
            projected_points=points,
            kickoff_time="2026-09-20T15:00:00+00:00",
            opponent_team_short_name="CHE",
            is_home=True,
        )
        for player_id, points in _points_for_gameweek(gameweek_number).items()
    ]


def _service(
    *,
    squad: CurrentSquadRecord | None,
    run: ProjectionRunRecord | None,
    rows_by_run: dict[int, list[PlayerProjectionFixtureRecord]],
    run_repository: _FakeProjectionRunRepository | None = None,
    projection_repository: _FakeMyTeamProjectionRepository | None = None,
) -> tuple[
    GetMyTeamRecommendationService, _FakeProjectionRunRepository, _FakeMyTeamProjectionRepository
]:
    run_repo = run_repository or _FakeProjectionRunRepository({"component_v3": run})
    projection_repo = projection_repository or _FakeMyTeamProjectionRepository(rows_by_run)
    service = GetMyTeamRecommendationService(
        _FakeCurrentSquadRepository(squad), run_repo, projection_repo
    )
    return service, run_repo, projection_repo


class TestNoSquad:
    def test_returns_none_when_no_squad_is_saved(self) -> None:
        service, _, _ = _service(squad=None, run=_run(1), rows_by_run={1: _rows_for_run(1)})

        assert service.execute() is None


class TestModelVersionSelection:
    def test_requests_the_default_model_version_explicitly(self) -> None:
        service, run_repository, _ = _service(
            squad=_squad(), run=_run(1), rows_by_run={1: _rows_for_run(1)}
        )

        service.execute()

        assert run_repository.requested_model_versions == ["component_v3"]

    def test_can_request_a_different_model_version_explicitly(self) -> None:
        run_repository = _FakeProjectionRunRepository({"baseline_v2": _run(7, "baseline_v2")})
        projection_repository = _FakeMyTeamProjectionRepository({7: _rows_for_run(7)})
        service, _, _ = _service(
            squad=_squad(),
            run=None,
            rows_by_run={},
            run_repository=run_repository,
            projection_repository=projection_repository,
        )

        service.execute(model_version="baseline_v2")

        assert run_repository.requested_model_versions == ["baseline_v2"]

    def test_no_run_for_the_model_is_an_explicit_failure(self) -> None:
        service, _, _ = _service(squad=_squad(), run=None, rows_by_run={})

        result = service.execute()

        assert isinstance(result, MyTeamRecommendationFailure)
        assert result.code == "no_projection_run"


class TestRunIdentity:
    def test_response_uses_the_resolved_runs_identity_not_a_recomputed_one(self) -> None:
        run = _run(42)
        service, _, projection_repository = _service(
            squad=_squad(), run=run, rows_by_run={42: _rows_for_run(42)}
        )

        result = service.execute()

        assert projection_repository.requested_run_ids == [42]
        assert result.projection_run_id == 42  # type: ignore[union-attr]
        assert result.model_version == "component_v3"  # type: ignore[union-attr]
        assert result.generated_at == RUN_GENERATED_AT  # type: ignore[union-attr]

    def test_projections_are_only_ever_fetched_for_the_resolved_run_id(self) -> None:
        # Even if rows exist for a different (older) run in the fake's data,
        # the service must only ask for the run get_latest resolved.
        older_run_rows = _rows_for_run(1)
        newer_run_rows = _rows_for_run(2)
        service, _, projection_repository = _service(
            squad=_squad(),
            run=_run(2),
            rows_by_run={1: older_run_rows, 2: newer_run_rows},
        )

        service.execute()

        assert projection_repository.requested_run_ids == [2]


class TestOptimiserWiring:
    def test_squad_and_projections_are_correctly_passed_into_the_optimiser(self) -> None:
        service, _, _ = _service(squad=_squad(), run=_run(1), rows_by_run={1: _rows_for_run(1)})

        result = service.execute()

        assert not isinstance(result, MyTeamRecommendationFailure)
        assert result is not None
        assert result.target_gameweek_number == 5
        assert result.player_projected_points[13] == 4.5

    def test_captain_vice_and_bench_come_from_the_engine_not_reimplemented(self) -> None:
        # Forward 13 projects highest (4.5) and forward 14 second (4.0) --
        # this only holds if optimise_lineup's own captain/vice logic ran.
        service, _, _ = _service(squad=_squad(), run=_run(1), rows_by_run={1: _rows_for_run(1)})

        result = service.execute()

        assert not isinstance(result, MyTeamRecommendationFailure)
        assert result is not None
        assert result.captain == 13
        assert result.vice_captain == 14
        assert len(result.starting_xi) == 11
        assert len(result.bench_outfield) == 3
        assert result.bench_goalkeeper == 2

    def test_starting_xi_and_captain_adjusted_points_match_the_engines_own_scoring(self) -> None:
        service, _, _ = _service(squad=_squad(), run=_run(1), rows_by_run={1: _rows_for_run(1)})

        result = service.execute()

        assert not isinstance(result, MyTeamRecommendationFailure)
        assert result is not None
        assert result.captain_adjusted_points == result.starting_xi_points + 4.5


class TestMissingProjections:
    def test_a_squad_player_missing_from_the_target_gameweek_is_an_explicit_failure(self) -> None:
        rows = [row for row in _rows_for_run(1) if row.player_id != 9]
        service, _, _ = _service(squad=_squad(), run=_run(1), rows_by_run={1: rows})

        result = service.execute()

        assert isinstance(result, MyTeamRecommendationFailure)
        assert result.code == "missing_player_projections"
        assert result.missing_player_ids == (9,)

    def test_never_falls_back_to_a_different_run_or_stale_data(self) -> None:
        # Rows exist for a *different* run only; the resolved run has none.
        service, _, projection_repository = _service(
            squad=_squad(), run=_run(1), rows_by_run={2: _rows_for_run(2)}
        )

        result = service.execute()

        assert isinstance(result, MyTeamRecommendationFailure)
        assert result.code == "missing_player_projections"
        assert projection_repository.requested_run_ids == [1]


class TestReadOnly:
    def test_computing_a_recommendation_does_not_expose_any_way_to_save_the_squad(self) -> None:
        # The fake current-squad repository has no save/upsert method at all --
        # structurally, the service cannot mutate the saved squad through it.
        service, _, _ = _service(squad=_squad(), run=_run(1), rows_by_run={1: _rows_for_run(1)})

        service.execute()

        assert not hasattr(service._current_squad_repository, "save_current")  # type: ignore[attr-defined]
