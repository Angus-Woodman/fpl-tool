import datetime as dt
from typing import Any

from api.db.session import get_db_session
from api.main import app
from api.repositories.current_squad_repository import (
    CurrentSquadPlayerRecord,
    CurrentSquadRecord,
)
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.routers.my_team import (
    get_current_squad_service,
    get_my_team_recommendation_service,
    get_upsert_current_squad_service,
)
from api.services.current_squad import UpsertCurrentSquadRequest, UpsertCurrentSquadService
from api.services.get_my_team_recommendation import (
    MyTeamRecommendation,
    MyTeamRecommendationFailure,
)
from api.services.get_my_team_view import (
    HorizonProjectionTotals,
    MyTeamPlayerViewRecord,
    MyTeamViewRecord,
    PlayerFixtureProjectionViewRecord,
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
                fixture_projections=[
                    PlayerFixtureProjectionViewRecord(
                        fixture_id=10,
                        gameweek_number=2,
                        projected_points=5.0,
                        kickoff_time="2026-08-15T15:00:00+00:00",
                        opponent_team_short_name="CHE",
                        is_home=True,
                    )
                ],
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
        gameweek_numbers=[2, 3, 4],
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
        assert payload["gameweek_numbers"] == [2, 3, 4]
        assert payload["players"][0]["web_name"] == "Saka"
        assert payload["players"][0]["projection_totals"]["horizon_3"] == 13.0
        assert payload["players"][0]["fixture_projections"][0]["opponent_team_short_name"] == "CHE"
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


def _full_squad_record(bank: float = 1.5, free_transfers: int = 2) -> CurrentSquadRecord:
    positions = ["GK"] + ["DEF"] * 4 + ["MID"] * 4 + ["FWD"] * 2 + ["GK", "DEF", "MID", "FWD"]
    return CurrentSquadRecord(
        squad_id=1,
        name="My Team",
        bank=bank,
        free_transfers=free_transfers,
        players=[
            CurrentSquadPlayerRecord(
                player_id=index + 1,
                web_name=f"P{index + 1}",
                first_name="First",
                second_name=f"P{index + 1}",
                team_name=f"Team {index % 5 + 1}",
                team_short_name=f"T{index % 5 + 1}",
                position=position,
                current_price=5.0,
                status="a",
                is_starting=index < 11,
                bench_order=None if index < 11 else index - 10,
                is_captain=index == 1,
                is_vice_captain=index == 2,
                team_id=index % 5 + 1,
            )
            for index, position in enumerate(positions)
        ],
    )


class _FakeFullUpsertService:
    def __init__(self) -> None:
        self.last_request: UpsertCurrentSquadRequest | None = None

    def execute(self, request: UpsertCurrentSquadRequest) -> CurrentSquadRecord:
        self.last_request = request
        return _full_squad_record(request.bank, request.free_transfers)


def test_us6_put_my_team_keeps_saving_the_whole_lineup_and_returns_authoritative_targets() -> None:
    service = _FakeFullUpsertService()
    session = _FakeSession()
    app.dependency_overrides[get_upsert_current_squad_service] = lambda: service
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        payload = _build_payload()
        response = TestClient(app).put("/my-team", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert (body["bank"], body["free_transfers"]) == (1.5, 2)
        assert session.committed is True
        assert service.last_request is not None
        assert service.last_request.bank == 1.5
        assert service.last_request.free_transfers == 2
        assert len(service.last_request.players) == 15
        offered = {
            (frozenset({c["first_player_id"], c["second_player_id"]}), c["kind"])
            for c in body["legal_rearrangements"]
        }
        assert (frozenset({2, 14}), "substitution") in offered
        assert (frozenset({13, 14}), "bench_priority") in offered
        assert not any(players & {12} and kind == "bench_priority" for players, kind in offered)
    finally:
        app.dependency_overrides.clear()


def test_us6_get_my_team_serialises_the_rearrangement_targets() -> None:
    from fpl_engine.rules import Rearrangement

    record = MyTeamViewRecord(
        squad_id=1,
        name="My Team",
        bank=1.5,
        free_transfers=2,
        players=[],
        projection_totals=None,
        bench_projection_totals=None,
        captain_adjusted_projection_totals=None,
        gameweek_numbers=[],
        legal_rearrangements=(
            Rearrangement(2, 14, "substitution"),
            Rearrangement(13, 14, "bench_priority"),
        ),
    )
    app.dependency_overrides[get_current_squad_service] = lambda: _FakeGetCurrentSquadService(
        record
    )
    try:
        response = TestClient(app).get("/my-team")

        assert response.status_code == 200
        assert response.json()["legal_rearrangements"] == [
            {"first_player_id": 2, "second_player_id": 14, "kind": "substitution"},
            {"first_player_id": 13, "second_player_id": 14, "kind": "bench_priority"},
        ]
    finally:
        app.dependency_overrides.clear()


def test_get_my_team_without_targets_still_returns_an_empty_list() -> None:
    record = MyTeamViewRecord(
        squad_id=1,
        name="My Team",
        bank=1.5,
        free_transfers=2,
        players=[],
        projection_totals=None,
        bench_projection_totals=None,
        captain_adjusted_projection_totals=None,
        gameweek_numbers=[],
    )
    app.dependency_overrides[get_current_squad_service] = lambda: _FakeGetCurrentSquadService(
        record
    )
    try:
        assert TestClient(app).get("/my-team").json()["legal_rearrangements"] == []
    finally:
        app.dependency_overrides.clear()


def test_put_my_team_rejects_an_illegal_starting_formation_with_400() -> None:
    # Real service + fakes: the router must surface the domain rule as a 400 without committing.
    repository = _FakeFormationRepository()
    lookup = _FakeFormationLookup()
    service = UpsertCurrentSquadService(repository, lookup)
    session = _FakeSession()
    app.dependency_overrides[get_upsert_current_squad_service] = lambda: service
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        payload = _build_payload()
        # Players 1 and 2 are both goalkeepers in the lookup, and both start.
        response = TestClient(app).put("/my-team", json=payload)

        assert response.status_code == 400
        assert response.json()["detail"] == "Starting XI must contain between 1 and 1 GK"
        assert repository.saved is False
        assert session.committed is False
        assert session.rolled_back is True
    finally:
        app.dependency_overrides.clear()


def test_put_my_team_rejects_a_non_tenth_bank_with_a_readable_400() -> None:
    repository = _FakeFormationRepository()
    service = UpsertCurrentSquadService(repository, _FakeFormationLookup())
    session = _FakeSession()
    app.dependency_overrides[get_upsert_current_squad_service] = lambda: service
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        payload = _build_payload()
        payload["bank"] = 0.55

        response = TestClient(app).put("/my-team", json=payload)

        assert response.status_code == 400
        assert response.json()["detail"].startswith("Bank must be a finite whole number of tenths")
        assert repository.saved is False
        assert session.committed is False
        assert session.rolled_back is True
    finally:
        app.dependency_overrides.clear()


class _FakeFormationRepository:
    def __init__(self) -> None:
        self.saved = False

    def get_current(self) -> CurrentSquadRecord | None:
        return None

    def save_current(self, *, bank: float, free_transfers: int, players: list[Any]) -> Any:
        self.saved = True
        raise AssertionError("an illegal formation must not be saved")


class _FakeFormationLookup:
    _POSITIONS = (
        ["GK", "GK"] + ["DEF"] * 4 + ["MID"] * 4 + ["FWD"] * 1 + ["DEF"] + ["MID"] + ["FWD"] * 2
    )

    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]:
        return [
            SquadPlayerLookupItem(
                player_id=player_id,
                team_id=player_id,
                web_name=f"P{player_id}",
                position=self._POSITIONS[player_id - 1],
                current_price=5.0,
            )
            for player_id in player_ids
        ]


class _FakeGetMyTeamRecommendationService:
    def __init__(self, result: MyTeamRecommendation | MyTeamRecommendationFailure | None) -> None:
        self._result = result

    def execute(
        self, model_version: str = "component_v3"
    ) -> MyTeamRecommendation | MyTeamRecommendationFailure | None:
        return self._result


def _recommendation() -> MyTeamRecommendation:
    return MyTeamRecommendation(
        model_version="component_v3",
        projection_run_id=42,
        generated_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC),
        target_gameweek_number=5,
        starting_xi_points=34.9,
        captain_adjusted_points=39.4,
        starting_xi=(1, 3, 4, 5, 6, 8, 9, 10, 13, 14, 15),
        bench_goalkeeper=2,
        bench_outfield=(7, 11, 12),
        captain=13,
        vice_captain=14,
        player_projected_points={1: 3.6, 13: 4.5},
        current_captain_adjusted_points=37.5,
    )


def test_get_my_team_recommendation_returns_404_when_no_squad() -> None:
    app.dependency_overrides[get_my_team_recommendation_service] = (
        lambda: _FakeGetMyTeamRecommendationService(None)
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/recommendation")

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_my_team_recommendation_returns_422_on_a_structured_failure() -> None:
    failure = MyTeamRecommendationFailure(
        code="missing_player_projections",
        message="2 squad player(s) have no component_v3 projection in run 42",
        missing_player_ids=(9, 12),
    )
    app.dependency_overrides[get_my_team_recommendation_service] = (
        lambda: _FakeGetMyTeamRecommendationService(failure)
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/recommendation")

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "missing_player_projections"
        assert detail["missing_player_ids"] == [9, 12]
    finally:
        app.dependency_overrides.clear()


def test_get_my_team_recommendation_returns_the_recommendation() -> None:
    app.dependency_overrides[get_my_team_recommendation_service] = (
        lambda: _FakeGetMyTeamRecommendationService(_recommendation())
    )
    try:
        client = TestClient(app)
        response = client.get("/my-team/recommendation")

        assert response.status_code == 200
        payload = response.json()
        assert payload["model_version"] == "component_v3"
        assert payload["projection_run_id"] == 42
        assert payload["captain"] == 13
        assert payload["vice_captain"] == 14
        assert payload["bench_goalkeeper"] == 2
        assert payload["bench_outfield"] == [7, 11, 12]
        assert len(payload["starting_xi"]) == 11
        assert payload["current_captain_adjusted_points"] == 37.5
    finally:
        app.dependency_overrides.clear()
