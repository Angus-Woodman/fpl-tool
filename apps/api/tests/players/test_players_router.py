from api.main import app
from api.repositories.player_read_repository import PlayerQueryResult, PlayerReadItem
from api.routers.players import get_list_players_service
from api.services.list_players import ListPlayersRequest
from fastapi.testclient import TestClient


class _FakeListPlayersService:
    def __init__(self) -> None:
        self.last_request: ListPlayersRequest | None = None

    def execute(self, request: ListPlayersRequest) -> PlayerQueryResult:
        self.last_request = request
        if request.search == "zzz":
            return PlayerQueryResult(
                items=[],
                total=0,
                page=request.page,
                page_size=request.page_size,
            )

        return PlayerQueryResult(
            items=[
                PlayerReadItem(
                    id=1,
                    web_name="Saka",
                    first_name="Bukayo",
                    second_name="Saka",
                    team_name="Arsenal",
                    team_short_name="ARS",
                    position="MID",
                    current_price=10.5,
                    status="a",
                )
            ],
            total=1,
            page=request.page,
            page_size=request.page_size,
        )


def test_players_route_returns_players() -> None:
    service = _FakeListPlayersService()
    app.dependency_overrides[get_list_players_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/players")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["web_name"] == "Saka"
    finally:
        app.dependency_overrides.clear()


def test_players_route_passes_filters_to_service() -> None:
    service = _FakeListPlayersService()
    app.dependency_overrides[get_list_players_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get(
            "/players",
            params={"search": "sak", "position": "MID", "sort": "price_desc", "page": 2},
        )

        assert response.status_code == 200
        assert service.last_request is not None
        assert service.last_request.search == "sak"
        assert service.last_request.position == "MID"
        assert service.last_request.sort == "price_desc"
        assert service.last_request.page == 2
    finally:
        app.dependency_overrides.clear()


def test_players_route_empty_response() -> None:
    service = _FakeListPlayersService()
    app.dependency_overrides[get_list_players_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/players", params={"search": "zzz"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 0
        assert payload["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_players_route_validation_error_for_invalid_page() -> None:
    service = _FakeListPlayersService()
    app.dependency_overrides[get_list_players_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/players", params={"page": 0})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
