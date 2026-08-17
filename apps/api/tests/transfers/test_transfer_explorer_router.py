import datetime as dt

from api.main import app
from api.routers.my_team import get_transfer_explorer_service
from api.services.get_transfer_explorer import (
    OutgoingPlayerSummary,
    RankedTransferCandidate,
    TransferExplorerFailure,
    TransferExplorerResult,
)
from fastapi.testclient import TestClient


class _FakeGetTransferExplorerService:
    def __init__(self, result: TransferExplorerResult | TransferExplorerFailure | None) -> None:
        self._result = result
        self.requested: list[tuple[int, int]] = []

    def execute(
        self, player_out_id: int, primary_horizon: int = 5
    ) -> TransferExplorerResult | TransferExplorerFailure | None:
        self.requested.append((player_out_id, primary_horizon))
        return self._result


def _result() -> TransferExplorerResult:
    return TransferExplorerResult(
        model_version="component_v3",
        projection_run_id=42,
        generated_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC),
        primary_horizon=5,
        bank=1.0,
        selling_price_is_approximate=True,
        outgoing=OutgoingPlayerSummary(
            player_id=9,
            web_name="Player9",
            position="MID",
            team_short_name="T9",
            current_price=5.0,
            selling_price=5.0,
            projected_points_by_horizon={1: 3.3, 3: 9.0, 5: 15.0},
        ),
        candidates=[
            RankedTransferCandidate(
                player_id=202,
                web_name="Candidate202",
                team_short_name="C55",
                price=5.0,
                resulting_bank=1.0,
                team_gain_by_horizon={1: 0.7, 3: 2.1, 5: 3.5},
                direct_xpts_difference=0.7,
                gameweeks_evaluated=3,
            )
        ],
        evaluated_gameweek_numbers=[5, 6, 7],
    )


def test_returns_404_when_no_squad_is_saved() -> None:
    app.dependency_overrides[get_transfer_explorer_service] = (
        lambda: _FakeGetTransferExplorerService(None)
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_returns_404_when_the_outgoing_player_does_not_exist() -> None:
    failure = TransferExplorerFailure(code="player_not_found", message="No player exists")
    app.dependency_overrides[get_transfer_explorer_service] = (
        lambda: _FakeGetTransferExplorerService(failure)
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/999999")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_returns_422_when_the_player_is_not_in_the_squad() -> None:
    failure = TransferExplorerFailure(
        code="player_not_in_squad", message="Player 9 is not in the current squad"
    )
    app.dependency_overrides[get_transfer_explorer_service] = (
        lambda: _FakeGetTransferExplorerService(failure)
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9")

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "player_not_in_squad"
    finally:
        app.dependency_overrides.clear()


def test_returns_the_ranked_candidates_and_forwards_the_primary_horizon() -> None:
    service = _FakeGetTransferExplorerService(_result())
    app.dependency_overrides[get_transfer_explorer_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9?primary_horizon=3")

        assert response.status_code == 200
        payload = response.json()
        assert payload["model_version"] == "component_v3"
        assert payload["projection_run_id"] == 42
        assert payload["outgoing"]["player_id"] == 9
        assert payload["candidates"][0]["player_id"] == 202
        assert service.requested == [(9, 3)]
    finally:
        app.dependency_overrides.clear()


def test_rejects_an_invalid_primary_horizon() -> None:
    app.dependency_overrides[get_transfer_explorer_service] = (
        lambda: _FakeGetTransferExplorerService(_result())
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9?primary_horizon=2")

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
