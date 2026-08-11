from typing import Any

from api.db.session import get_db_session
from api.main import app
from api.repositories.current_squad_repository import (
    CurrentSquadPlayerRecord,
    CurrentSquadRecord,
)
from api.routers.my_team import get_current_squad_service, get_upsert_current_squad_service
from api.services.current_squad import UpsertCurrentSquadRequest
from api.services.get_my_team_view import (
    HorizonProjectionTotals,
    MyTeamPlayerViewRecord,
    MyTeamViewRecord,
)
from fastapi.testclient import TestClient


class _FakeGetCurrentSquadService:
    def __init__(self, result: MyTeamViewRecord | None) -> None:
        self._result = result

    def execute(self) -> MyTeamViewRecord | None:
        return self._result


class _FakeUpsertCurrentSquadService:
    def __init__(self) -> None:
        self.last_request: UpsertCurrentSquadRequest | None = None

    def execute(self, request: UpsertCurrentSquadRequest) -> CurrentSquadRecord:
        self.last_request = request
        return CurrentSquadRecord(
            squad_id=1,
            name="My Team",
            bank=request.bank,
            free_transfers=request.free_transfers,
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


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _payload_player(
    player_id: int,
    *,
    is_starting: bool,
    bench_order: int | None,
    is_captain: bool = False,
    is_vice_captain: bool = False,
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "is_starting": is_starting,
        "bench_order": bench_order,
        "is_captain": is_captain,
        "is_vice_captain": is_vice_captain,
    }


def _build_payload() -> dict[str, Any]:
    return {
        "bank": 1.5,
        "free_transfers": 2,
        "players": [
            _payload_player(1, is_starting=True, bench_order=None, is_captain=True),
            _payload_player(2, is_starting=True, bench_order=None, is_vice_captain=True),
            _payload_player(3, is_starting=True, bench_order=None),
            _payload_player(4, is_starting=True, bench_order=None),
            _payload_player(5, is_starting=True, bench_order=None),
            _payload_player(6, is_starting=True, bench_order=None),
            _payload_player(7, is_starting=True, bench_order=None),
            _payload_player(8, is_starting=True, bench_order=None),
            _payload_player(9, is_starting=True, bench_order=None),
            _payload_player(10, is_starting=True, bench_order=None),
            _payload_player(11, is_starting=True, bench_order=None),
            _payload_player(12, is_starting=False, bench_order=1),
            _payload_player(13, is_starting=False, bench_order=2),
            _payload_player(14, is_starting=False, bench_order=3),
            _payload_player(15, is_starting=False, bench_order=4),
        ],
    }


def test_get_my_team_returns_404_when_missing() -> None:
    app.dependency_overrides[get_current_squad_service] = lambda: _FakeGetCurrentSquadService(None)
    try:
        client = TestClient(app)
        response = client.get("/my-team")

        assert response.status_code == 404
        assert response.json()["detail"] == "No squad saved yet"
    finally:
        app.dependency_overrides.clear()


def test_get_my_team_returns_current_squad() -> None:
    record = MyTeamViewRecord(
        squad_id=1,
        name="My Team",
        bank=1.5,
        free_transfers=2,
        players=[
            MyTeamPlayerViewRecord(
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
                projection_totals=HorizonProjectionTotals(
                    horizon_1=5.0,
                    horizon_3=13.0,
                    horizon_5=18.0,
                ),
            )
        ],
        projection_totals=HorizonProjectionTotals(
            horizon_1=5.0,
            horizon_3=13.0,
            horizon_5=18.0,
        ),
        bench_projection_totals=None,
        captain_adjusted_projection_totals=HorizonProjectionTotals(
            horizon_1=10.0,
            horizon_3=26.0,
            horizon_5=36.0,
        ),
    )
    app.dependency_overrides[get_current_squad_service] = lambda: _FakeGetCurrentSquadService(
        record
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team")

        assert response.status_code == 200
        payload = response.json()
        assert payload["name"] == "My Team"
        assert payload["projection_totals"]["horizon_1"] == 5.0
        assert payload["captain_adjusted_projection_totals"]["horizon_1"] == 10.0
        assert payload["players"][0]["web_name"] == "Saka"
        assert payload["players"][0]["projection_totals"]["horizon_3"] == 13.0
    finally:
        app.dependency_overrides.clear()


def test_put_my_team_returns_saved_squad() -> None:
    service = _FakeUpsertCurrentSquadService()
    session = _FakeSession()
    app.dependency_overrides[get_upsert_current_squad_service] = lambda: service
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        client = TestClient(app)
        response = client.put("/my-team", json=_build_payload())

        assert response.status_code == 200
        payload = response.json()
        assert payload["bank"] == 1.5
        assert payload["players"][0]["is_captain"] is True
        assert service.last_request is not None
        assert service.last_request.free_transfers == 2
        assert session.committed is True
        assert session.rolled_back is False
    finally:
        app.dependency_overrides.clear()
