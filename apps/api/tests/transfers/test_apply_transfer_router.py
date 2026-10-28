from api.db.session import get_db_session
from api.main import app
from api.routers.my_team import get_apply_transfer_service
from api.services.apply_transfer import ApplyTransferFailure
from api.services.get_my_team_view import MyTeamViewRecord
from fastapi.testclient import TestClient


class _FakeApplyTransferService:
    def __init__(self, result: MyTeamViewRecord | ApplyTransferFailure | None) -> None:
        self._result = result
        self.requested: list[tuple[int, int]] = []

    def execute(
        self, player_out_id: int, player_in_id: int
    ) -> MyTeamViewRecord | ApplyTransferFailure | None:
        self.requested.append((player_out_id, player_in_id))
        return self._result


def _view_record() -> MyTeamViewRecord:
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


def test_returns_404_when_no_squad_is_saved() -> None:
    app.dependency_overrides[get_apply_transfer_service] = lambda: _FakeApplyTransferService(None)
    try:
        client = TestClient(app)
        response = client.post("/my-team/transfers/9/apply", json={"player_in_id": 202})

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_returns_404_when_the_incoming_player_does_not_exist() -> None:
    failure = ApplyTransferFailure(code="player_not_found", message="No player exists")
    app.dependency_overrides[get_apply_transfer_service] = lambda: _FakeApplyTransferService(
        failure
    )
    try:
        client = TestClient(app)
        response = client.post("/my-team/transfers/9/apply", json={"player_in_id": 999999})

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_returns_422_when_the_transfer_is_illegal() -> None:
    failure = ApplyTransferFailure(
        code="transfer_illegal",
        message="This transfer is not legal: insufficient_bank",
        errors=("insufficient_bank",),
    )
    app.dependency_overrides[get_apply_transfer_service] = lambda: _FakeApplyTransferService(
        failure
    )
    try:
        client = TestClient(app)
        response = client.post("/my-team/transfers/9/apply", json={"player_in_id": 202})

        assert response.status_code == 422
        payload = response.json()["detail"]
        assert payload["code"] == "transfer_illegal"
        assert payload["errors"] == ["insufficient_bank"]
    finally:
        app.dependency_overrides.clear()


class _FakeDbSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_returns_422_with_the_pool_reason_and_rolls_back_without_committing() -> None:
    failure = ApplyTransferFailure(
        code="transfer_illegal",
        message="Candidate202 is not currently selectable in FPL.",
        errors=("player_not_selectable",),
    )
    session = _FakeDbSession()
    app.dependency_overrides[get_apply_transfer_service] = lambda: _FakeApplyTransferService(
        failure
    )
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        client = TestClient(app)
        response = client.post("/my-team/transfers/9/apply", json={"player_in_id": 202})

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "transfer_illegal"
        assert detail["errors"] == ["player_not_selectable"]
        assert session.rollbacks == 1
        assert session.commits == 0
    finally:
        app.dependency_overrides.clear()


def test_applies_and_returns_the_updated_my_team_state() -> None:
    service = _FakeApplyTransferService(_view_record())
    app.dependency_overrides[get_apply_transfer_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post("/my-team/transfers/9/apply", json={"player_in_id": 202})

        assert response.status_code == 200
        payload = response.json()
        assert payload["squad_id"] == 1
        assert payload["bank"] == 1.0
        assert service.requested == [(9, 202)]
    finally:
        app.dependency_overrides.clear()


def test_returns_422_with_the_invalid_money_code_and_rolls_back() -> None:
    failure = ApplyTransferFailure(
        code="invalid_money", message="Bank must be a finite whole number of tenths"
    )
    session = _FakeDbSession()
    app.dependency_overrides[get_apply_transfer_service] = lambda: _FakeApplyTransferService(
        failure
    )
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        response = TestClient(app).post("/my-team/transfers/9/apply", json={"player_in_id": 202})

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_money"
        assert session.commits == 0
        assert session.rollbacks == 1
    finally:
        app.dependency_overrides.clear()
