import datetime as dt

from api.main import app
from api.routers.my_team import get_transfer_preview_service
from api.services.get_transfer_preview import (
    LineupSummary,
    TransferPreviewFailure,
    TransferPreviewResult,
)
from fastapi.testclient import TestClient


class _FakeGetTransferPreviewService:
    def __init__(self, result: TransferPreviewResult | TransferPreviewFailure | None) -> None:
        self._result = result
        self.requested: list[tuple[int, int]] = []

    def execute(
        self, player_out_id: int, player_in_id: int
    ) -> TransferPreviewResult | TransferPreviewFailure | None:
        self.requested.append((player_out_id, player_in_id))
        return self._result


def _lineup(*, captain: int, vice_captain: int) -> LineupSummary:
    return LineupSummary(
        starting_xi=(1, 3, 4, 5, 8, 10, 12, 13, 14, 15, 202),
        bench_goalkeeper=2,
        bench_outfield=(6, 7, 11),
        captain=captain,
        vice_captain=vice_captain,
        starting_xi_points=35.0,
        captain_adjusted_points=39.5,
    )


def _result() -> TransferPreviewResult:
    return TransferPreviewResult(
        model_version="component_v3",
        projection_run_id=42,
        generated_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC),
        target_gameweek_number=5,
        bank=1.0,
        resulting_bank=1.0,
        selling_price_is_approximate=True,
        player_out_id=9,
        player_in_id=202,
        is_legal=True,
        errors=(),
        projected_team_gain=0.7,
        direct_player_xpts_difference=0.7,
        lineup_before=_lineup(captain=13, vice_captain=14),
        lineup_after=_lineup(captain=13, vice_captain=14),
        captain_changed=False,
        vice_captain_changed=False,
        player_in_status="i",
    )


def test_returns_404_when_no_squad_is_saved() -> None:
    app.dependency_overrides[get_transfer_preview_service] = lambda: _FakeGetTransferPreviewService(
        None
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9/preview?player_in_id=202")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_returns_404_when_the_incoming_player_does_not_exist() -> None:
    failure = TransferPreviewFailure(code="player_not_found", message="No player exists")
    app.dependency_overrides[get_transfer_preview_service] = lambda: _FakeGetTransferPreviewService(
        failure
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9/preview?player_in_id=999999")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_returns_422_when_the_outgoing_player_is_not_in_the_squad() -> None:
    failure = TransferPreviewFailure(
        code="player_not_in_squad", message="Player 9 is not in the current squad"
    )
    app.dependency_overrides[get_transfer_preview_service] = lambda: _FakeGetTransferPreviewService(
        failure
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9/preview?player_in_id=202")

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "player_not_in_squad"
    finally:
        app.dependency_overrides.clear()


def test_returns_422_with_structured_detail_when_the_incoming_player_is_not_in_the_pool() -> None:
    failure = TransferPreviewFailure(
        code="player_not_in_candidate_pool",
        message="Candidate202 is not currently selectable in FPL.",
    )
    app.dependency_overrides[get_transfer_preview_service] = lambda: _FakeGetTransferPreviewService(
        failure
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9/preview?player_in_id=202")

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "code": "player_not_in_candidate_pool",
            "message": "Candidate202 is not currently selectable in FPL.",
            "missing_player_ids": [],
        }
    finally:
        app.dependency_overrides.clear()


def test_returns_the_preview_and_forwards_both_player_ids() -> None:
    service = _FakeGetTransferPreviewService(_result())
    app.dependency_overrides[get_transfer_preview_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9/preview?player_in_id=202")

        assert response.status_code == 200
        payload = response.json()
        assert payload["is_legal"] is True
        assert payload["lineup_before"]["captain"] == 13
        assert payload["lineup_after"]["captain"] == 13
        assert payload["captain_changed"] is False
        assert payload["player_in_status"] == "i"
        assert service.requested == [(9, 202)]
    finally:
        app.dependency_overrides.clear()


def test_returns_an_illegal_preview_as_a_normal_200_response() -> None:
    illegal_result = TransferPreviewResult(
        model_version="component_v3",
        projection_run_id=42,
        generated_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC),
        target_gameweek_number=5,
        bank=0.0,
        resulting_bank=-994.0,
        selling_price_is_approximate=True,
        player_out_id=9,
        player_in_id=202,
        is_legal=False,
        errors=("insufficient_bank",),
        projected_team_gain=0.0,
        direct_player_xpts_difference=0.7,
        lineup_before=_lineup(captain=13, vice_captain=14),
        lineup_after=None,
        captain_changed=False,
        vice_captain_changed=False,
        player_in_status="i",
    )
    app.dependency_overrides[get_transfer_preview_service] = lambda: _FakeGetTransferPreviewService(
        illegal_result
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/transfers/9/preview?player_in_id=202")

        assert response.status_code == 200
        payload = response.json()
        assert payload["is_legal"] is False
        assert payload["errors"] == ["insufficient_bank"]
        assert payload["lineup_after"] is None
        # Status is advisory: carried separately, never folded into the legality errors.
        assert payload["player_in_status"] == "i"
    finally:
        app.dependency_overrides.clear()
