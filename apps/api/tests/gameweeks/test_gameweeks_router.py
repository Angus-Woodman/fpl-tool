from api.main import app
from api.repositories.gameweek_read_repository import GameweekReadItem
from api.routers.gameweeks import get_list_gameweeks_service
from api.services.list_gameweeks import GameweekListResult
from fastapi.testclient import TestClient


class _FakeListGameweeksService:
    def execute(self) -> GameweekListResult:
        return GameweekListResult(
            items=[
                GameweekReadItem(
                    id=1,
                    number=1,
                    name="Gameweek 1",
                    is_current=False,
                    is_next=True,
                    is_finished=False,
                ),
                GameweekReadItem(
                    id=2,
                    number=2,
                    name="Gameweek 2",
                    is_current=True,
                    is_next=False,
                    is_finished=False,
                ),
            ],
            total=2,
        )


def test_gameweeks_route_returns_items() -> None:
    app.dependency_overrides[get_list_gameweeks_service] = _FakeListGameweeksService
    try:
        client = TestClient(app)
        response = client.get("/gameweeks")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert payload["items"][1]["is_current"] is True
    finally:
        app.dependency_overrides.clear()
