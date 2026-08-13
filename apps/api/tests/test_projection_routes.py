import datetime as dt

from api.db.session import get_db_session
from api.main import app
from api.routers.projections import get_generate_projections_service
from api.services.generate_projections import GenerateProjectionsSummary
from fastapi.testclient import TestClient


class _FakeService:
    def execute(self) -> GenerateProjectionsSummary:
        return GenerateProjectionsSummary(
            projections_generated=120,
            fixtures_considered=10,
            players_considered=80,
            model_version="baseline-v1",
            generated_at=dt.datetime(2026, 1, 1, 9, 30, tzinfo=dt.UTC),
        )


class _FailingService:
    def execute(self) -> GenerateProjectionsSummary:
        raise RuntimeError("projection refresh failed")


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_projection_refresh_runs_and_commits() -> None:
    session = _FakeSession()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_generate_projections_service] = lambda: _FakeService()
    try:
        client = TestClient(app)
        response = client.post("/projections/run")

        assert response.status_code == 200
        payload = response.json()
        assert payload["projections_generated"] == 120
        assert payload["fixtures_considered"] == 10
        assert payload["players_considered"] == 80
        assert payload["model_version"] == "baseline-v1"
        assert payload["generated_at"] == "2026-01-01T09:30:00+00:00"
        assert session.committed is True
        assert session.rolled_back is False
    finally:
        app.dependency_overrides.clear()


def test_projection_refresh_rolls_back_on_failure() -> None:
    session = _FakeSession()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_generate_projections_service] = lambda: _FailingService()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/projections/run")

        assert response.status_code == 500
        assert session.committed is False
        assert session.rolled_back is True
    finally:
        app.dependency_overrides.clear()
