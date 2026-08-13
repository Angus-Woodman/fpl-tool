from api.main import app
from api.repositories.fixture_read_repository import (
    FixtureTickerItem,
    FixtureTickerResult,
)
from api.routers.fixtures import get_list_fixture_ticker_service
from api.services.list_fixtures import ListFixtureTickerRequest
from fastapi.testclient import TestClient


class _FakeFixtureTickerService:
    def __init__(self) -> None:
        self.last_request: ListFixtureTickerRequest | None = None

    def execute(self, request: ListFixtureTickerRequest) -> FixtureTickerResult:
        self.last_request = request
        return FixtureTickerResult(
            items=[
                FixtureTickerItem(
                    fixture_id=1,
                    gameweek_number=2,
                    kickoff_time="2026-08-21T18:30:00+00:00",
                    home_team_short_name="ARS",
                    away_team_short_name="AVL",
                    home_team_difficulty=3,
                    away_team_difficulty=4,
                    finished=False,
                )
            ],
            total=1,
            page=1,
            page_size=20,
        )


def test_fixture_ticker_route_returns_items() -> None:
    service = _FakeFixtureTickerService()
    app.dependency_overrides[get_list_fixture_ticker_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/fixtures/ticker")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["page"] == 1
        assert payload["page_size"] == 20
        assert payload["items"][0]["home_team_short_name"] == "ARS"
    finally:
        app.dependency_overrides.clear()


def test_fixture_ticker_route_passes_limit() -> None:
    service = _FakeFixtureTickerService()
    app.dependency_overrides[get_list_fixture_ticker_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get(
            "/fixtures/ticker",
            params={"page": 2, "limit": 8, "team_id": 3, "gameweek": 6},
        )

        assert response.status_code == 200
        assert service.last_request is not None
        assert service.last_request.page == 2
        assert service.last_request.page_size == 8
        assert service.last_request.team_id == 3
        assert service.last_request.gameweek == 6
    finally:
        app.dependency_overrides.clear()


def test_fixture_ticker_route_validation_error() -> None:
    service = _FakeFixtureTickerService()
    app.dependency_overrides[get_list_fixture_ticker_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/fixtures/ticker", params={"limit": 0})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_fixture_ticker_route_page_validation_error() -> None:
    service = _FakeFixtureTickerService()
    app.dependency_overrides[get_list_fixture_ticker_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/fixtures/ticker", params={"page": 0})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_fixture_ticker_route_gameweek_validation_error() -> None:
    service = _FakeFixtureTickerService()
    app.dependency_overrides[get_list_fixture_ticker_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.get("/fixtures/ticker", params={"gameweek": 39})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
