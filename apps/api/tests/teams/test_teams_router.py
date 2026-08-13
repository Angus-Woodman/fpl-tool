from api.main import app
from api.repositories.team_read_repository import TeamReadItem
from api.routers.teams import get_list_teams_service, get_update_team_difficulty_service
from api.services.list_teams import TeamListResult
from api.services.update_team_difficulty import UpdateTeamDifficultyRequest
from fastapi.testclient import TestClient


class _FakeListTeamsService:
    def execute(self) -> TeamListResult:
        return TeamListResult(
            items=[
                TeamReadItem(id=1, name="Arsenal", short_name="ARS", difficulty=4),
                TeamReadItem(id=2, name="Aston Villa", short_name="AVL", difficulty=2),
            ],
            total=2,
        )


def test_teams_route_returns_items() -> None:
    app.dependency_overrides[get_list_teams_service] = _FakeListTeamsService
    try:
        client = TestClient(app)
        response = client.get("/teams")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert payload["items"][0]["short_name"] == "ARS"
    finally:
        app.dependency_overrides.clear()


class _FakeUpdateTeamDifficultyService:
    def __init__(self, result: TeamReadItem | None) -> None:
        self._result = result
        self.last_request: UpdateTeamDifficultyRequest | None = None

    def execute(self, request: UpdateTeamDifficultyRequest) -> TeamReadItem | None:
        self.last_request = request
        return self._result


def test_update_team_difficulty_route_returns_updated_team() -> None:
    service = _FakeUpdateTeamDifficultyService(
        TeamReadItem(id=1, name="Arsenal", short_name="ARS", difficulty=5)
    )
    app.dependency_overrides[get_update_team_difficulty_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.patch("/teams/1", json={"difficulty": 5})

        assert response.status_code == 200
        payload = response.json()
        assert payload["difficulty"] == 5
        assert service.last_request == UpdateTeamDifficultyRequest(team_id=1, difficulty=5)
    finally:
        app.dependency_overrides.clear()


def test_update_team_difficulty_route_returns_404_when_missing() -> None:
    service = _FakeUpdateTeamDifficultyService(None)
    app.dependency_overrides[get_update_team_difficulty_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.patch("/teams/999", json={"difficulty": 3})

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_update_team_difficulty_route_validates_range() -> None:
    service = _FakeUpdateTeamDifficultyService(
        TeamReadItem(id=1, name="Arsenal", short_name="ARS", difficulty=1)
    )
    app.dependency_overrides[get_update_team_difficulty_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.patch("/teams/1", json={"difficulty": 6})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
