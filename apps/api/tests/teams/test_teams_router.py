from api.main import app
from api.repositories.team_read_repository import TeamReadItem
from api.routers.teams import get_list_teams_service
from api.services.list_teams import TeamListResult
from fastapi.testclient import TestClient


class _FakeListTeamsService:
    def execute(self) -> TeamListResult:
        return TeamListResult(
            items=[
                TeamReadItem(id=1, name="Arsenal", short_name="ARS"),
                TeamReadItem(id=2, name="Aston Villa", short_name="AVL"),
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
