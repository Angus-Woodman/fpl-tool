from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from api.main import app
from api.repositories.plan_repository import PlanNotFoundError, PlanNotReadyError
from api.routers.plan_transfers import (
    get_plan_transfer_analysis_service,
    get_planning_context_resolver,
)
from api.services.plan_context import PlanningContext
from api.services.plan_transfer_analysis import PlanTransferAnalysisService
from explorer_builders import (
    FakeLookup,
    FakePlayers,
    FakeProjections,
    FakeRuns,
    FakeSchedule,
    FakeTeams,
    candidate_records,
    context_for,
    flat_points,
    plan,
    run_record,
)
from fastapi.testclient import TestClient
from fpl_engine.rules import RuleViolationError

Resolver = Callable[[int, int], PlanningContext]
URL = "/plans/1/gameweeks/8/transfers/6"


def service(
    *, runs: FakeRuns | None = None, records: list | None = None
) -> PlanTransferAnalysisService:
    return PlanTransferAnalysisService(
        players=FakePlayers(records),
        lookup=FakeLookup(records),
        runs=runs if runs is not None else FakeRuns(run_record()),
        projections=FakeProjections(flat_points(range(8, 14), {6: 2.0, 106: 5.0})),
        schedule=FakeSchedule(),
        teams=FakeTeams(),
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    def build(
        analysis: PlanTransferAnalysisService | None = None, resolver: Resolver | None = None
    ) -> TestClient:
        reference = plan()
        app.dependency_overrides[get_planning_context_resolver] = lambda: (
            resolver
            or (lambda plan_id, gameweek: context_for(reference, gameweek, plan_id=plan_id))
        )
        app.dependency_overrides[get_plan_transfer_analysis_service] = lambda: analysis or service()
        return TestClient(app)

    yield build  # type: ignore[misc]
    app.dependency_overrides.clear()


def test_a_planner_list_names_the_context_it_was_computed_for(client) -> None:  # type: ignore[no-untyped-def]
    response = client().get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["planning_context"] == {"plan_id": 1, "gameweek": 8, "revision": 3}
    assert body["plan"]["gameweek"] == 8 and body["plan"]["revision"] == 3
    assert set(body["projection"]) >= {
        "model_version",
        "run_id",
        "generated_at",
        "newer_run_available",
        "primary_horizon",
        "horizons",
        "limited_to_selected_gameweek",
        "limited_reason",
    }
    assert body["outgoing"]["operation"] == "add_transfer"
    assert "selling_price_is_approximate" not in body["outgoing"]
    candidate = body["candidates"][0]
    assert set(candidate["best_xi_gain_by_horizon"]) == {"1", "3", "5"}
    assert set(candidate["plan_impact_by_horizon"]) == {"1", "3", "5"}
    assert candidate["state"] in {"available", "unavailable", "blocked_by_later_decision"}
    assert isinstance(candidate["price_tenths"], int)


def test_primary_horizon_and_run_are_passed_through(client) -> None:  # type: ignore[no-untyped-def]
    runs = FakeRuns(run_record(1), run_record(2, hours=3))
    response = client(service(runs=runs)).get(
        URL, params={"primary_horizon": 3, "projection_run_id": 1}
    )

    body = response.json()
    assert body["projection"]["primary_horizon"] == 3
    assert body["projection"]["run_id"] == 1
    assert body["projection"]["newer_run_available"] is True


@pytest.mark.parametrize("value", [0, 2, 4, 6])
def test_only_horizons_one_three_and_five_are_accepted(client, value: int) -> None:  # type: ignore[no-untyped-def]
    response = client().get(URL, params={"primary_horizon": value})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_horizon"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (PlanNotFoundError(1), 404, "plan_not_found"),
        (PlanNotReadyError(1), 409, "plan_not_ready"),
        (RuleViolationError("gameweek_not_in_plan", "outside"), 422, "gameweek_not_in_plan"),
        (RuleViolationError("evaluation_blocked", "blocked"), 422, "evaluation_blocked"),
    ],
)
def test_context_resolution_errors_are_explicit(  # type: ignore[no-untyped-def]
    client, error: Exception, status: int, code: str
) -> None:
    def failing(plan_id: int, gameweek: int) -> PlanningContext:
        raise error

    response = client(resolver=failing).get(URL)

    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


def test_analysis_failures_map_to_their_codes(client) -> None:  # type: ignore[no-untyped-def]
    cases = {
        "no_projection_run": service(runs=FakeRuns()),
        "selectability_unknown": service(
            records=candidate_records(overrides={114: {"can_select": None}})
        ),
    }
    for code, analysis in cases.items():
        response = client(analysis).get(URL)
        assert response.status_code == 422, code
        assert response.json()["detail"]["code"] == code
    pinned = client().get(URL, params={"projection_run_id": 99})
    assert pinned.status_code == 422 and pinned.json()["detail"]["code"] == "run_not_found"
    absent = client().get("/plans/1/gameweeks/8/transfers/107")
    assert absent.status_code == 422 and absent.json()["detail"]["code"] == "player_not_in_squad"


def test_missing_squad_projections_list_the_players(client) -> None:  # type: ignore[no-untyped-def]
    points = flat_points(range(8, 14), {6: 2.0})
    for week in points.values():
        del week[5]
    analysis = PlanTransferAnalysisService(
        players=FakePlayers(),
        lookup=FakeLookup(),
        runs=FakeRuns(run_record()),
        projections=FakeProjections(points),
        schedule=FakeSchedule(),
        teams=FakeTeams(),
    )

    response = client(analysis).get(URL)

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "missing_projections",
        "message": response.json()["detail"]["message"],
        "missing_player_ids": [5],
    }


def test_the_my_team_explorer_routes_are_still_registered_separately() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/my-team/transfers/{player_out_id}" in paths
    assert "/plans/{plan_id}/gameweeks/{gameweek}/transfers/{player_out_id}" in paths


PREVIEW = f"{URL}/preview"


def test_a_confirmable_preview_returns_the_commit_descriptor_for_its_revision(client) -> None:  # type: ignore[no-untyped-def]
    response = client().get(PREVIEW, params={"player_in_id": 106})

    assert response.status_code == 200
    body = response.json()
    assert body["planning_context"] == {"plan_id": 1, "gameweek": 8, "revision": 3}
    assert body["confirmable"] is True and body["state"] == "available"
    commit = body["commit"]
    assert commit["expected_revision"] == body["planning_context"]["revision"] == 3
    assert commit["intent"] == {
        "kind": "add_transfer",
        "gameweek_number": 8,
        "outgoing_player_id": 6,
        "outgoing_ownership_id": "00000000-0000-0000-0000-0000000003ee",
        "incoming_player_id": 106,
    }
    assert commit["guard"] == {
        "expected_outgoing_market_tenths": 54,
        "expected_incoming_price_tenths": 50,
    }
    assert body["candidate"]["player_id"] == 106
    assert set(body["totals"]) == {"1", "3", "5"}
    assert set(body["best_xi"]["gain_by_horizon"]) == {"1", "3", "5"}
    assert set(body["lineup_effect"]) == {"captain_changed", "vice_captain_changed"}
    first = body["gameweeks"][0]
    assert first["basis"] == "saved_plan" and first["valid"] is True
    assert set(first["accounting"]) == {"before", "after"}


def test_unavailable_candidates_preview_as_200_without_a_commit(client) -> None:  # type: ignore[no-untyped-def]
    response = client().get(
        "/plans/1/gameweeks/8/transfers/7/preview", params={"player_in_id": 201}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "unavailable" and body["reasons"] == ["club_limit"]
    assert body["confirmable"] is False and body["commit"] is None


def test_preview_pins_the_run_and_reports_the_error_table(client) -> None:  # type: ignore[no-untyped-def]
    runs = FakeRuns(run_record(1), run_record(2, hours=3))
    pinned = client(service(runs=runs)).get(
        PREVIEW, params={"player_in_id": 106, "projection_run_id": 1}
    )
    assert pinned.json()["projection"]["run_id"] == 1
    assert pinned.json()["projection"]["newer_run_available"] is True

    unknown = client().get(PREVIEW, params={"player_in_id": 9999})
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "player_not_found"
    owned = client().get(PREVIEW, params={"player_in_id": 7})
    assert owned.status_code == 422
    assert owned.json()["detail"]["code"] == "player_not_in_candidate_pool"
    no_run = client(service(runs=FakeRuns())).get(PREVIEW, params={"player_in_id": 106})
    assert no_run.status_code == 422 and no_run.json()["detail"]["code"] == "no_projection_run"
    missing_param = client().get(PREVIEW)
    assert missing_param.status_code == 422


def test_preview_resolution_errors_are_explicit(client) -> None:  # type: ignore[no-untyped-def]
    def failing(plan_id: int, gameweek: int) -> PlanningContext:
        raise PlanNotReadyError(plan_id)

    response = client(resolver=failing).get(PREVIEW, params={"player_in_id": 106})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "plan_not_ready"
