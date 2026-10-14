from __future__ import annotations

from typing import Any

import pytest
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
from test_plan_services import guarded_mutations as guarded_mutations


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

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "planner_writer_retired"


def test_adjusting_the_horizon_extends_the_plan() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)

    response = client.patch(f"/plans/{plan_id}", json={"end_gameweek": 6})

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "planner_writer_retired"


def test_save_gameweek_with_chip() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)

    response = client.put(
        f"/plans/{plan_id}/gameweeks/2",
        json={"chip": "BENCH_BOOST", "players": _squad_payload()},
    )

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "planner_writer_retired"


def test_retired_writer_never_validates_or_accepts_a_squad_payload() -> None:
    client = _client(FakePlanRepository())
    plan_id = _create_plan(client)
    payload = _squad_payload()
    expensive = next(player for player in payload if player["player_id"] == 12)
    expensive["player_id"] = 21

    response = client.put(
        f"/plans/{plan_id}/gameweeks/2",
        json={"chip": None, "players": payload},
    )

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "planner_writer_retired"


def test_delete_plan() -> None:
    repository = FakePlanRepository()
    client = _client(repository)
    plan_id = _create_plan(client)

    assert client.delete(f"/plans/{plan_id}").status_code == 204
    assert repository.get(plan_id) is None


@pytest.fixture
def guarded_client(request, planner_session):
    from api.repositories.plan_repository import PlanRepository
    from api.routers.plans import get_plan_repository

    service, plan_id = request.getfixturevalue("guarded_mutations")
    from api.routers.plans import get_plan_mutation_service

    app.dependency_overrides[get_db_session] = lambda: planner_session
    app.dependency_overrides[get_plan_repository] = lambda: PlanRepository(planner_session)
    app.dependency_overrides[get_plan_mutation_service] = lambda: service
    app.dependency_overrides[get_plan_view_service] = lambda: GetPlanViewService(
        _EmptyProjectionRepository()
    )
    with TestClient(app) as client:
        yield client, plan_id


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_retired_writers_change_no_sql_rows_and_never_open_database_dependency(
    guarded_client,
    planner_session,
):
    from api.models.entities import (
        PlanGameweekModel,
        PlanGameweekPlayerModel,
        PlanModel,
        PlanMutationModel,
        PlanStartingPlayerModel,
        PlanTransferDecisionModel,
    )
    from sqlalchemy import select

    client, plan_id = guarded_client
    models = (
        PlanModel,
        PlanGameweekModel,
        PlanGameweekPlayerModel,
        PlanStartingPlayerModel,
        PlanTransferDecisionModel,
        PlanMutationModel,
    )

    def snapshot():
        return [
            list(planner_session.execute(select(model.__table__).order_by(model.id)).mappings())
            for model in models
        ]

    before = snapshot()
    planner_session.rollback()

    def forbidden_database_dependency():
        raise AssertionError("Retired writer opened a database session")

    app.dependency_overrides[get_db_session] = forbidden_database_dependency
    for method, url in (("PATCH", f"/plans/{plan_id}"), ("PUT", f"/plans/{plan_id}/gameweeks/8")):
        response = client.request(method, url, json={"bank": 999, "players": []})
        assert response.status_code == 410
        assert response.json()["detail"]["code"] == "planner_writer_retired"
    assert snapshot() == before


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_http_contracts_and_canonical_get(guarded_client):
    from test_plan_services import mutation_body

    client, plan_id = guarded_client
    body = mutation_body().model_dump(mode="json")
    response = client.post(f"/plans/{plan_id}/mutations", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "committed"
    assert response.json()["plan"]["revision"] == 1
    current = client.get(f"/plans/{plan_id}")
    assert current.status_code == 200
    assert current.json()["starting_state"]["free_transfers"] == 1
    assert (
        client.get(f"/plans/{plan_id}/mutations/{body['mutation_id']}").json()["status"]
        == "already_committed"
    )
    assert (
        client.post(f"/plans/{plan_id}/mutations", json=body).json()["status"]
        == "already_committed"
    )
    stale = mutation_body(2).model_dump(mode="json")
    assert (
        client.post(f"/plans/{plan_id}/mutations", json=stale).json()["detail"]["code"]
        == "revision_conflict"
    )
    invalid = mutation_body(3, 1, [{"kind": "set_starting_transfers", "value": None}]).model_dump(
        mode="json"
    )
    domain = client.post(f"/plans/{plan_id}/mutations", json=invalid)
    assert domain.status_code == 422
    assert isinstance(domain.json()["detail"], dict)
    invalid["expected_revision"] = True
    schema = client.post(f"/plans/{plan_id}/mutations", json=invalid)
    assert schema.status_code == 422
    assert isinstance(schema.json()["detail"], list)
    assert (
        client.get(f"/plans/{plan_id}/mutations/00000000-0000-0000-0000-000000009999").status_code
        == 404
    )


@pytest.mark.skipif(
    __import__("os").getenv("RUN_PLANNER_BROWSER_TESTS") != "1",
    reason="Requires guarded SQL, installed Playwright and a running frontend",
)
def test_horizon_chip_history_through_actual_browser_and_api(
    guarded_client, planner_session, planner_plan, planner_metadata
):
    import os
    import socket
    import subprocess
    from dataclasses import replace
    from pathlib import Path
    from threading import Thread

    import httpx
    import uvicorn
    from api.repositories.plan_repository import PlanRepository
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import GameweekDecision
    from fpl_engine.rules import Chip

    _, plan_id = guarded_client
    repository = PlanRepository(planner_session)
    plan = replace(
        planner_plan,
        start_gameweek=25,
        end_gameweek=26,
        boundary=replace(planner_plan.boundary, used_chips=frozenset({Chip.WILDCARD})),
        gameweeks=tuple(
            GameweekDecision(number, planner_plan.boundary.lineup) for number in (25, 26)
        ),
    )
    repository.save_canonical(plan_id, plan, evaluate_plan(plan, planner_metadata))
    planner_session.commit()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/plans/{plan_id}")
            assert response.status_code == 200, response.text
            result = subprocess.run(
                [
                    "pnpm",
                    "--filter",
                    "web",
                    "e2e",
                    "tests/e2e/planner-foundations.spec.ts",
                    "--grep",
                    "real API horizon",
                    "--workers=1",
                    "--reporter=line",
                ],
                cwd=Path(__file__).parents[4],
                env={
                    **os.environ,
                    "PLANNER_TEST_API_URL": f"http://127.0.0.1:{port}",
                    "PLANNER_TEST_PLAN_ID": str(plan_id),
                },
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
    reopened = repository.load_canonical(plan_id)
    assert reopened.start_gameweek == 19
    assert not reopened.boundary.used_chips
    assert all(week.chip is None for week in reopened.gameweeks)


@pytest.mark.parametrize("failure", ["missing_gameweek", "invalid_price", "invalid_bank"])
@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_pending_get_exposes_retryable_initialization_reason_without_writes(
    guarded_client, planner_session, planner_plan, failure
):
    from api.models.entities import PlanModel, PlanStartingPlayerModel, PlayerModel
    from api.repositories.plan_repository import PlanPlayerSave, PlanRepository
    from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
    from api.services.initialize_planner_foundations import InitializePlannerFoundationsService
    from sqlalchemy import func, select

    client, _ = guarded_client
    repository = PlanRepository(planner_session)
    plan_id = repository.create(
        name="Retry initialization",
        start_gameweek=8,
        end_gameweek=10,
        initial_bank=1.0,
        initial_free_transfers=1,
    )

    def save_week(number):
        repository.save_gameweek(
            plan_id,
            number,
            chip=None,
            bank=1.0,
            free_transfers_available=1,
            transfers_made=0,
            points_hit=0,
            players=[
                PlanPlayerSave(
                    player.player_id,
                    role.is_starting,
                    role.bench_order,
                    role.is_captain,
                    role.is_vice_captain,
                )
                for player, role in zip(
                    planner_plan.boundary.players, planner_plan.boundary.lineup, strict=True
                )
            ],
        )

    for number in (8, 9, 10):
        if number != 9 or failure != "missing_gameweek":
            save_week(number)
    if failure == "invalid_price":
        planner_session.get(PlayerModel, 1).current_price = 5.55
    if failure == "invalid_bank":
        planner_session.get(PlanModel, plan_id).initial_bank = 1.11
    planner_session.commit()
    initializer = InitializePlannerFoundationsService(
        planner_session, SquadPlayerLookupRepository(planner_session)
    )
    report = initializer.execute(plan_id, apply=True)
    assert report.status == "legacy_pending"
    response = client.get(f"/plans/{plan_id}")
    assert response.status_code == 200, response.text
    assert response.json()["initialization"] == {
        "ready": False,
        "reason": "; ".join(report.diagnostics)
        + ". Repair stored plan/player data and retry initialization.",
        "retryable": True,
    }
    row = planner_session.get(PlanModel, plan_id)
    assert row.foundation_state == "legacy_pending"
    assert row.revision == 0
    assert (
        planner_session.scalar(
            select(func.count())
            .select_from(PlanStartingPlayerModel)
            .where(PlanStartingPlayerModel.plan_id == plan_id)
        )
        == 0
    )
    save_week(9)
    planner_session.get(PlayerModel, 1).current_price = 5.0
    row.initial_bank = 1.0
    planner_session.commit()
    repaired = client.get(f"/plans/{plan_id}")
    assert repaired.status_code == 200
    assert repaired.json()["initialization"]["reason"] == "Explicit initialization required"
    assert repaired.json()["foundation_state"] == "legacy_pending"
    assert initializer.execute(plan_id, apply=True).status == "initialized"
    assert client.get(f"/plans/{plan_id}").json()["initialization"]["ready"] is True


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_guarded_committed_response_loss_is_reconciled_without_second_write(
    guarded_client, monkeypatch
):
    from test_plan_services import mutation_body

    client, plan_id = guarded_client
    original = GetPlanViewService.execute

    def lose_enrichment(*args, **kwargs):
        raise RuntimeError("Injected post-commit enrichment failure")

    monkeypatch.setattr(GetPlanViewService, "execute", lose_enrichment)
    body = mutation_body().model_dump(mode="json")
    response = client.post(f"/plans/{plan_id}/mutations", json=body)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "outcome_unknown"
    monkeypatch.setattr(GetPlanViewService, "execute", original)
    receipt = client.get(f"/plans/{plan_id}/mutations/{body['mutation_id']}")
    assert receipt.status_code == 200
    assert receipt.json()["committed_revision"] == 1
    assert client.post(f"/plans/{plan_id}/mutations", json=body).json()["plan"]["revision"] == 1
