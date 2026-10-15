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


def _saved(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Live prices are enrichment and may change; every saved field must not.
    return [
        {key: value for key, value in decision.items() if "live" not in key}
        for decision in decisions
    ]


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


@pytest.mark.parametrize(
    ("start", "setup", "attempt", "reason"),
    [
        *[
            (
                17,
                [{"kind": "activate_chip", "gameweek_number": 18, "chip": chip}],
                {"kind": "activate_chip", "gameweek_number": 19, "chip": chip},
                "Planned for gameweek 18",
            )
            for chip in ("WILDCARD", "FREE_HIT", "BENCH_BOOST", "TRIPLE_CAPTAIN")
        ],
        (
            17,
            [{"kind": "set_starting_chips", "used_chips": ["FREE_HIT"]}],
            {"kind": "activate_chip", "gameweek_number": 18, "chip": "FREE_HIT"},
            "Used before this plan",
        ),
        (
            17,
            [{"kind": "activate_chip", "gameweek_number": 18, "chip": "WILDCARD"}],
            {"kind": "activate_chip", "gameweek_number": 18, "chip": "BENCH_BOOST"},
            "Remove the existing chip",
        ),
        (
            17,
            [
                {"kind": "activate_chip", "gameweek_number": 18, "chip": "WILDCARD"},
                {"kind": "activate_chip", "gameweek_number": 19, "chip": "BENCH_BOOST"},
            ],
            {"kind": "move_chip", "source_gameweek": 18, "target_gameweek": 19, "chip": "WILDCARD"},
            "source/target has changed",
        ),
        *[
            (
                1,
                [],
                {"kind": "activate_chip", "gameweek_number": 1, "chip": chip},
                "unavailable in gameweek 1",
            )
            for chip in ("WILDCARD", "FREE_HIT")
        ],
        *[
            (
                19,
                [{"kind": "activate_chip", "gameweek_number": first, "chip": "FREE_HIT"}],
                {"kind": "activate_chip", "gameweek_number": second, "chip": "FREE_HIT"},
                f"Free Hit conflicts with gameweek {first}",
            )
            for first, second in ((19, 20), (20, 19))
        ],
        (
            20,
            [{"kind": "set_starting_chips", "used_chips": [], "free_hit_gameweek_19": True}],
            {"kind": "activate_chip", "gameweek_number": 20, "chip": "FREE_HIT"},
            "Free Hit conflicts with gameweek 19",
        ),
        (
            20,
            [{"kind": "activate_chip", "gameweek_number": 20, "chip": "FREE_HIT"}],
            {"kind": "set_starting_chips", "used_chips": [], "free_hit_gameweek_19": True},
            "Free Hit conflicts with gameweek 19",
        ),
    ],
)
@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_chip_http_bypass_rejects_with_engine_reason_and_zero_writes(
    guarded_client, planner_session, start, setup, attempt, reason
):
    from api.models.entities import PlanModel
    from sqlalchemy import select
    from test_plan_services import mutation_body

    client, plan_id = guarded_client
    horizon = client.post(
        f"/plans/{plan_id}/mutations",
        json=mutation_body(
            100, 0, [{"kind": "change_horizon", "start_gameweek": start, "end_gameweek": 22}]
        ).model_dump(mode="json"),
    )
    assert horizon.status_code == 200, horizon.text
    revision = 1
    if setup:
        response = client.post(
            f"/plans/{plan_id}/mutations",
            json=mutation_body(101, revision, setup).model_dump(mode="json"),
        )
        assert response.status_code == 200, response.text
        revision += 1
    tables = [table for name, table in PlanModel.metadata.tables.items() if name.startswith("plan")]

    def snapshot():
        return [
            list(
                planner_session.execute(
                    select(table).order_by(*table.primary_key.columns)
                ).mappings()
            )
            for table in tables
        ]

    before = snapshot()
    planner_session.rollback()
    current = client.get(f"/plans/{plan_id}").json()
    response = client.post(
        f"/plans/{plan_id}/mutations",
        json=mutation_body(102, revision, [attempt]).model_dump(mode="json"),
    )
    assert response.status_code == 422, response.text
    assert reason in response.json()["detail"]["message"]
    assert snapshot() == before
    assert client.get(f"/plans/{plan_id}").json() == current


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_chip_http_clear_move_reset_and_reopen_use_only_canonical_chip(
    guarded_client, planner_session
):
    from api.models.entities import PlanChip, PlanGameweekModel, PlayerModel
    from sqlalchemy import select
    from test_plan_services import mutation_body

    client, plan_id = guarded_client
    revision = 0

    def mutate(intents):
        nonlocal revision
        response = client.post(
            f"/plans/{plan_id}/mutations",
            json=mutation_body(200 + revision, revision, intents).model_dump(mode="json"),
        )
        assert response.status_code == 200, response.text
        revision += 1
        return response.json()["plan"]

    mutate([{"kind": "change_horizon", "start_gameweek": 17, "end_gameweek": 22}])
    mutate([{"kind": "set_starting_chips", "used_chips": ["FREE_HIT"]}])
    boundary = client.get(f"/plans/{plan_id}").json()["starting_state"]
    outgoing = next(player for player in boundary["players"] if player["player_id"] == 2)
    captured = mutate(
        [
            {
                "kind": "add_transfer",
                "gameweek_number": 18,
                "outgoing_player_id": 2,
                "outgoing_ownership_id": outgoing["ownership_id"],
                "incoming_player_id": 102,
            }
        ]
    )
    frozen = captured["gameweeks"][1]["decisions"]
    planner_session.get(PlayerModel, 102).current_price = 9.0
    legacy = planner_session.scalar(
        select(PlanGameweekModel).where(
            PlanGameweekModel.plan_id == plan_id, PlanGameweekModel.gameweek_number == 18
        )
    )
    legacy.chip = PlanChip.WILDCARD
    planner_session.commit()
    planned = mutate([{"kind": "activate_chip", "gameweek_number": 18, "chip": "WILDCARD"}])
    assert planned["gameweeks"][0]["chip_availability"]["WILDCARD"]["conflicting_gameweek"] == 18
    assert planned["gameweeks"][0]["chip_availability"]["FREE_HIT"]["state"] == "used_before"
    assert planned["gameweeks"][3]["chip_availability"]["FREE_HIT"]["state"] == "available"
    assert planned["gameweeks"][3]["chip_availability"]["WILDCARD"]["state"] == "available"
    moved = mutate(
        [{"kind": "move_chip", "source_gameweek": 18, "target_gameweek": 19, "chip": "WILDCARD"}]
    )
    assert moved["gameweeks"][1]["chip"] is None
    assert (
        moved["gameweeks"][0]["chip_availability"]["WILDCARD"]["reason"]
        == "Planned for gameweek 19"
    )
    cleared = mutate(
        [
            {
                "kind": "remove_chip",
                "gameweek_number": 19,
                "chip": "WILDCARD",
                "expected_chip": "WILDCARD",
            }
        ]
    )
    reopened = client.get(f"/plans/{plan_id}").json()
    assert reopened == cleared
    assert all(week["chip"] is None for week in reopened["gameweeks"])
    assert all(
        week["chip_availability"]["WILDCARD"]["state"] == "available"
        for week in reopened["gameweeks"]
    )
    assert _saved(reopened["gameweeks"][1]["decisions"]) == _saved(frozen)
    assert all(
        not week["decisions"] for week in reopened["gameweeks"] if week["gameweek_number"] != 18
    )
    assert planner_session.get(PlanGameweekModel, legacy.id).chip == PlanChip.WILDCARD


@pytest.mark.parametrize("journey", ["horizon", "chips", "transfers", "pricing", "persistence"])
@pytest.mark.skipif(
    __import__("os").getenv("RUN_PLANNER_BROWSER_TESTS") != "1",
    reason="Requires guarded SQL, installed Playwright and a running frontend",
)
def test_planner_story_through_actual_browser_and_api(
    guarded_client, planner_session, planner_plan, planner_metadata, journey, tmp_path, monkeypatch
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

    client, plan_id = guarded_client
    repository = PlanRepository(planner_session)
    start, end = {
        "horizon": (25, 26),
        "chips": (17, 22),
        "transfers": (8, 12),
        "pricing": (8, 11),
        "persistence": (8, 10),
    }[journey]
    plan = replace(
        planner_plan,
        start_gameweek=start,
        end_gameweek=end,
        boundary=replace(
            planner_plan.boundary,
            free_transfers=2 if journey == "transfers" else planner_plan.boundary.free_transfers,
            used_chips=frozenset()
            if journey in ("transfers", "pricing", "persistence")
            else frozenset({Chip.WILDCARD if journey == "horizon" else Chip.FREE_HIT}),
        ),
        gameweeks=tuple(
            GameweekDecision(number, planner_plan.boundary.lineup)
            for number in range(start, end + 1)
        ),
    )
    repository.save_canonical(plan_id, plan, evaluate_plan(plan, planner_metadata))
    planner_session.commit()
    frozen = []
    if journey == "transfers":
        from api.models.entities import PlayerModel
        from test_plan_services import mutation_body

        for identifier in (2, 3, 4, 5, 6):
            planner_session.get(PlayerModel, identifier).current_price = 5.4
        planner_session.commit()
        for revision, (number, identifiers) in enumerate(((8, (2,)), (10, (3, 4, 5, 6)))):
            response = client.post(
                f"/plans/{plan_id}/mutations",
                json=mutation_body(
                    950 + revision,
                    revision,
                    [
                        {
                            "kind": "add_transfer",
                            "gameweek_number": number,
                            "outgoing_player_id": identifier,
                            "outgoing_ownership_id": str(
                                next(
                                    player.ownership_id
                                    for player in plan.boundary.players
                                    if player.player_id == identifier
                                )
                            ),
                            "incoming_player_id": identifier + 100,
                        }
                        for identifier in identifiers
                    ],
                ).model_dump(mode="json"),
            )
            assert response.status_code == 200, response.text
        planner_session.get(PlayerModel, 105).current_price = 8.0
        planner_session.get(PlayerModel, 113).current_price = 5.2
        planner_session.commit()
    fault_file = tmp_path / "canonical-write-fault"
    if journey == "persistence":
        from api.models.entities import PlayerModel
        from api.repositories.plan_repository import PlanRepository as FaultRepository
        from sqlalchemy.exc import SQLAlchemyError

        planner_session.get(PlayerModel, 102).current_price = 9.0
        planner_session.commit()
        real_save = FaultRepository.save_canonical

        def save_unless_faulted(*args, **kwargs):
            if fault_file.exists():
                raise SQLAlchemyError("Injected canonical write failure after receipt")
            return real_save(*args, **kwargs)

        monkeypatch.setattr(FaultRepository, "save_canonical", save_unless_faulted)
    if journey == "pricing":
        from api.models.entities import PlayerModel
        from test_plan_services import mutation_body

        planner_session.get(PlayerModel, 2).current_price = 5.4
        planner_session.get(PlayerModel, 102).current_price = 6.2
        planner_session.commit()
        outgoing = next(player for player in plan.boundary.players if player.player_id == 2)
        response = client.post(
            f"/plans/{plan_id}/mutations",
            json=mutation_body(
                960,
                0,
                [
                    {
                        "kind": "add_transfer",
                        "gameweek_number": 8,
                        "outgoing_player_id": 2,
                        "outgoing_ownership_id": str(outgoing.ownership_id),
                        "incoming_player_id": 102,
                    }
                ],
            ).model_dump(mode="json"),
        )
        assert response.status_code == 200, response.text
        planner_session.get(PlayerModel, 2).current_price = 5.6
        planner_session.get(PlayerModel, 102).current_price = 6.0
        planner_session.commit()
    if journey == "chips":
        from api.models.entities import PlayerModel
        from test_plan_services import mutation_body

        outgoing = next(player for player in plan.boundary.players if player.player_id == 2)
        response = client.post(
            f"/plans/{plan_id}/mutations",
            json=mutation_body(
                900,
                0,
                [
                    {
                        "kind": "add_transfer",
                        "gameweek_number": 18,
                        "outgoing_player_id": 2,
                        "outgoing_ownership_id": str(outgoing.ownership_id),
                        "incoming_player_id": 102,
                    }
                ],
            ).model_dump(mode="json"),
        )
        assert response.status_code == 200, response.text
        frozen = response.json()["plan"]["gameweeks"][1]["decisions"]
        planner_session.get(PlayerModel, 102).current_price = 9.0
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
                    {
                        "horizon": "real API horizon",
                        "chips": "US2 real API chips",
                        "transfers": "US3 real API transfers",
                        "pricing": "US4 real API pricing",
                        "persistence": "US5 real API persistence",
                    }[journey],
                    "--workers=1",
                    "--reporter=line",
                ],
                cwd=Path(__file__).parents[4],
                env={
                    **os.environ,
                    "PLANNER_TEST_API_URL": f"http://127.0.0.1:{port}",
                    "PLANNER_TEST_PLAN_ID": str(plan_id),
                    "PLANNER_FAULT_FILE": str(fault_file),
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
    assert (
        reopened.start_gameweek
        == {
            "horizon": 19,
            "chips": 1,
            "transfers": 8,
            "pricing": 9,
            "persistence": 8,
        }[journey]
    )
    assert not reopened.boundary.used_chips
    assert all(week.chip is None for week in reopened.gameweeks)
    if journey == "transfers":
        assert sum(len(week.transfers) for week in reopened.gameweeks) == 6
        assert reopened.gameweeks[0].transfers[0].incoming_player_id == 113
        assert reopened.gameweeks[3].transfers[0].outgoing_player_id == 113
        assert (
            reopened.gameweeks[3].transfers[0].outgoing_ownership_id
            == reopened.gameweeks[0].transfers[0].incoming_ownership_id
        )
        assert not evaluate_plan(reopened, planner_metadata).diagnostics
    if journey == "persistence":
        assert reopened.revision == 9
        assert reopened.name == "Second tab"
        assert not fault_file.exists()
        assert not any(week.transfers for week in reopened.gameweeks)
        by_slot = {p.slot_id: p.player_id for p in reopened.boundary.players}

        def roles(number):
            lineup = next(w.lineup for w in reopened.gameweeks if w.gameweek_number == number)
            return (
                next(by_slot[r.slot_id] for r in lineup if r.is_captain),
                next(by_slot[r.slot_id] for r in lineup if r.is_vice_captain),
            )

        assert roles(9) == (10, 9)
        assert roles(8) == roles(10) == (2, 3)
        assert reopened.boundary.bank_tenths == 10
    if journey == "pricing":
        decision = reopened.gameweeks[0].transfers[0]
        carried = next(p for p in reopened.boundary.players if p.player_id == 113)
        assert sum(len(week.transfers) for week in reopened.gameweeks) == 1
        assert (decision.outgoing_player_id, decision.incoming_player_id) == (113, 102)
        assert (decision.outgoing_market_tenths, decision.incoming_price_tenths) == (50, 60)
        assert (carried.purchase_price_tenths, carried.provenance.original_price_tenths) == (48, 50)
        assert reopened.boundary.bank_tenths == 12
        evaluation = evaluate_plan(reopened, planner_metadata)
        assert not evaluation.diagnostics
        assert evaluation.earliest_shortfall_gameweek is None
    if journey == "chips":
        current = client.get(f"/plans/{plan_id}").json()
        assert _saved(
            next(week for week in current["gameweeks"] if week["gameweek_number"] == 18)[
                "decisions"
            ]
        ) == _saved(frozen)
        assert sum(len(week["decisions"]) for week in current["gameweeks"]) == 1


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


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us4_http_exposes_basis_saved_quotes_live_prices_and_shortfall(
    guarded_client, planner_session, planner_plan
):
    from api.models.entities import PlayerModel
    from test_plan_services import mutation_body

    client, plan_id = guarded_client
    owned = next(p for p in planner_plan.boundary.players if p.player_id == 2)
    planner_session.get(PlayerModel, 2).current_price = 5.4
    planner_session.get(PlayerModel, 102).current_price = 6.2
    planner_session.commit()

    def post(number, revision, intents):
        response = client.post(
            f"/plans/{plan_id}/mutations",
            json=mutation_body(number, revision, intents).model_dump(mode="json"),
        )
        assert response.status_code == 200, response.text
        return response.json()["plan"]

    saved = post(
        1,
        0,
        [
            {
                "kind": "add_transfer",
                "gameweek_number": 8,
                "outgoing_player_id": 2,
                "outgoing_ownership_id": str(owned.ownership_id),
                "incoming_player_id": 102,
            }
        ],
    )
    quote = saved["gameweeks"][0]["decisions"][0]
    assert (quote["outgoing_market_tenths"], quote["incoming_price_tenths"]) == (54, 62)
    assert (quote["purchase_price_tenths"], quote["selling_price_tenths"]) == (50, 52)
    assert (quote["basis_kind"], quote["basis_confirmation"]) == ("starting", "assumed")
    assert saved["financial_status"]["earliest_shortfall_gameweek"] is None
    planner_session.get(PlayerModel, 2).current_price = 5.6
    planner_session.get(PlayerModel, 102).current_price = 6.0
    planner_session.commit()
    refreshed = client.get(f"/plans/{plan_id}").json()["gameweeks"][0]["decisions"][0]
    assert _saved([refreshed]) == _saved([quote])
    assert (refreshed["outgoing_live_market_tenths"], refreshed["incoming_live_price_tenths"]) == (
        56,
        60,
    )
    corrected = post(
        2,
        1,
        [
            {
                "kind": "correct_purchase_price",
                "ownership_id": str(owned.ownership_id),
                "price_tenths": 48,
            }
        ],
    )
    decision = corrected["gameweeks"][0]["decisions"][0]
    assert (decision["purchase_price_tenths"], decision["selling_price_tenths"]) == (48, 51)
    assert decision["basis_confirmation"] == "user_confirmed"
    assert (decision["outgoing_market_tenths"], decision["incoming_price_tenths"]) == (54, 62)
    status = corrected["financial_status"]
    assert (status["earliest_shortfall_gameweek"], status["earliest_shortfall_tenths"]) == (8, 1)
    assert status["requires_resolution"] is True
    assert "gameweek 8" in status["earliest_shortfall_reason"]
    assert corrected["gameweeks"][0]["accounting"]["closing_bank_tenths"] == -1


def _post(client, plan_id, number, revision, intents=None):
    from test_plan_services import mutation_body

    return client.post(
        f"/plans/{plan_id}/mutations",
        json=mutation_body(number, revision, intents).model_dump(mode="json"),
    )


def _receipt(client, plan_id, number):
    from uuid import UUID

    return client.get(f"/plans/{plan_id}/mutations/{UUID(int=number)}")


def _fail_canonical_writes(monkeypatch):
    from api.repositories.plan_repository import PlanRepository
    from sqlalchemy.exc import SQLAlchemyError

    original = PlanRepository.save_canonical

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Injected accepted write failure")

    monkeypatch.setattr(PlanRepository, "save_canonical", fail)
    return lambda: monkeypatch.setattr(PlanRepository, "save_canonical", original)


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us5_http_pending_candidate_exists_only_while_its_base_is_compatible(
    guarded_client, monkeypatch
):
    client, plan_id = guarded_client
    restore = _fail_canonical_writes(monkeypatch)
    failed = _post(client, plan_id, 1, 0)
    assert failed.status_code == 503
    detail = failed.json()["detail"]
    assert (detail["code"], detail["mutation_id"]) == (
        "accepted_not_saved",
        "00000000-0000-0000-0000-000000000001",
    )
    assert detail["plan"]["revision"] == 0 and detail["plan"]["name"] != "Renamed"
    assert detail["candidate"]["name"] == "Renamed"
    pending = _receipt(client, plan_id, 1)
    assert pending.status_code == 200
    assert pending.json()["status"] == "accepted_not_saved"
    assert pending.json()["candidate"]["name"] == "Renamed"
    assert client.get(f"/plans/{plan_id}").json()["revision"] == 0
    restore()
    other = _post(client, plan_id, 2, 0, [{"kind": "rename_plan", "name": "Other tab"}])
    assert other.status_code == 200
    for stale in (_receipt(client, plan_id, 1), _post(client, plan_id, 1, 0)):
        assert stale.status_code == 409
        body = stale.json()["detail"]
        assert body["code"] == "stale_reprepare_required"
        assert body["candidate"] is None
        assert body["plan"]["name"] == "Other tab" and body["plan"]["revision"] == 1
        assert body["intent_metadata"] is not None
    assert client.get(f"/plans/{plan_id}").json()["name"] == "Other tab"


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us5_http_committed_id_wins_over_a_stale_revision_and_never_overlays_the_old_candidate(
    guarded_client,
):
    client, plan_id = guarded_client
    first = _post(client, plan_id, 1, 0, [{"kind": "rename_plan", "name": "First"}])
    assert first.status_code == 200
    second = _post(client, plan_id, 2, 1, [{"kind": "rename_plan", "name": "Second"}])
    assert second.json()["plan"]["revision"] == 2
    retry = _post(client, plan_id, 1, 0, [{"kind": "rename_plan", "name": "First"}])
    assert retry.status_code == 200, retry.text
    body = retry.json()
    assert (body["status"], body["committed_revision"]) == ("already_committed", 1)
    assert body["plan"]["revision"] == 2 and body["plan"]["name"] == "Second"
    assert body["candidate"] is None
    lookup = _receipt(client, plan_id, 1).json()
    assert (lookup["status"], lookup["committed_revision"]) == ("already_committed", 1)
    assert lookup["plan"]["name"] == "Second" and lookup["candidate"] is None
    fresh = _post(client, plan_id, 3, 0, [{"kind": "rename_plan", "name": "Third"}])
    assert fresh.status_code == 409
    assert fresh.json()["detail"]["code"] == "revision_conflict"
    assert fresh.json()["detail"]["plan"]["revision"] == 2
    assert _receipt(client, plan_id, 3).status_code == 404
    assert client.get(f"/plans/{plan_id}").json()["revision"] == 2


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us5_http_same_id_retry_after_an_inconclusive_404_commits_exactly_once(guarded_client):
    client, plan_id = guarded_client
    unknown = _receipt(client, plan_id, 7)
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "mutation_not_found"
    first = _post(client, plan_id, 7, 0)
    assert first.status_code == 200
    assert first.json()["committed_revision"] == 1
    duplicate = _post(client, plan_id, 7, 0)
    assert duplicate.json()["status"] == "already_committed"
    assert _receipt(client, plan_id, 7).json()["status"] == "already_committed"
    assert client.get(f"/plans/{plan_id}").json()["revision"] == 1
    changed = _post(client, plan_id, 7, 0, [{"kind": "rename_plan", "name": "Different"}])
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "mutation_id_reused"
    assert client.get(f"/plans/{plan_id}").json()["name"] == "Renamed"


@pytest.mark.skipif(__import__("os").getenv("RUN_DB_TESTS") != "1", reason="Requires guarded SQL")
def test_us5_http_missing_plan_is_distinct_from_an_unknown_receipt(guarded_client):
    client, plan_id = guarded_client
    missing = _post(client, plan_id + 999, 1, 0)
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "plan_not_found"
    lookup = _receipt(client, plan_id + 999, 1)
    assert lookup.status_code == 404
    assert lookup.json()["detail"]["code"] == "plan_not_found"
    unknown = _receipt(client, plan_id, 12345)
    assert unknown.json()["detail"]["code"] == "mutation_not_found"
