from __future__ import annotations

from typing import Any

from api.db.session import get_db_session
from api.main import app
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.routers.plans import (
    get_create_plan_service,
    get_delete_plan_service,
    get_get_plan_service,
    get_list_plans_service,
    get_plan_view_service,
    get_save_plan_gameweek_service,
    get_update_plan_service,
)
from api.services.get_plan_view import GetPlanViewService
from api.services.plans import (
    CreatePlanService,
    DeletePlanService,
    GetPlanService,
    ListPlansService,
    SavePlanGameweekService,
    UpdatePlanService,
)
from builders import FakePlayerLookupRepository, build_squad
from fastapi.testclient import TestClient
from test_plan_services import FakeCurrentSquadRepository, FakePlanRepository


class _FakeSession:
    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _EmptyProjectionRepository:
    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]:
        return []


def _squad_payload() -> list[dict[str, Any]]:
    return [
        {
            "player_id": player.player_id,
            "is_starting": player.is_starting,
            "bench_order": player.bench_order,
            "is_captain": player.is_captain,
            "is_vice_captain": player.is_vice_captain,
        }
        for player in build_squad()
    ]


def _client(repository: FakePlanRepository) -> TestClient:
    app.dependency_overrides[get_db_session] = lambda: _FakeSession()
    app.dependency_overrides[get_plan_view_service] = lambda: GetPlanViewService(
        _EmptyProjectionRepository()
    )
    app.dependency_overrides[get_list_plans_service] = lambda: ListPlansService(repository)
    app.dependency_overrides[get_get_plan_service] = lambda: GetPlanService(repository)
    app.dependency_overrides[get_create_plan_service] = lambda: CreatePlanService(
        repository, FakeCurrentSquadRepository()
    )
    app.dependency_overrides[get_update_plan_service] = lambda: UpdatePlanService(repository)
    app.dependency_overrides[get_delete_plan_service] = lambda: DeletePlanService(repository)
    app.dependency_overrides[get_save_plan_gameweek_service] = lambda: SavePlanGameweekService(
        repository, FakePlayerLookupRepository()
    )
    return TestClient(app)


def _create_plan(client: TestClient) -> int:
    response = client.post(
        "/plans",
        json={"name": "No Haaland GW1", "start_gameweek": 1, "end_gameweek": 4},
    )
    assert response.status_code == 201
    plan_id: int = response.json()["plan_id"]
    return plan_id


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_create_plan_returns_every_gameweek() -> None:
    client = _client(FakePlanRepository())

    response = client.post(
        "/plans",
        json={"name": "No Haaland GW1", "start_gameweek": 1, "end_gameweek": 4},
    )

    body = response.json()
    assert response.status_code == 201
    assert body["name"] == "No Haaland GW1"
    assert [gameweek["gameweek_number"] for gameweek in body["gameweeks"]] == [1, 2, 3, 4]


def test_get_plan_returns_404_when_missing() -> None:
    client = _client(FakePlanRepository())

    assert client.get("/plans/99").status_code == 404


def test_rename_plan() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)

    response = client.patch(f"/plans/{plan_id}", json={"name": "Haaland In GW2"})

    assert response.status_code == 200
    assert response.json()["name"] == "Haaland In GW2"


def test_adjusting_the_horizon_extends_the_plan() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)

    response = client.patch(f"/plans/{plan_id}", json={"end_gameweek": 6})

    numbers = [gameweek["gameweek_number"] for gameweek in response.json()["gameweeks"]]
    assert numbers == [1, 2, 3, 4, 5, 6]


def test_save_gameweek_with_chip() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)

    response = client.put(
        f"/plans/{plan_id}/gameweeks/2",
        json={"chip": "BENCH_BOOST", "players": _squad_payload()},
    )

    assert response.status_code == 200
    assert response.json()["gameweeks"][1]["chip"] == "BENCH_BOOST"


def test_rule_violation_returns_422_with_a_code() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)
    payload = _squad_payload()
    expensive = next(player for player in payload if player["player_id"] == 12)
    expensive["player_id"] = 21

    response = client.put(
        f"/plans/{plan_id}/gameweeks/2",
        json={"chip": None, "players": payload},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "budget"


def test_delete_plan() -> None:
    repository = FakePlanRepository()
    client = _client(repository)
    plan_id = _create_plan(client)

    assert client.delete(f"/plans/{plan_id}").status_code == 204
    assert repository.get(plan_id) is None
