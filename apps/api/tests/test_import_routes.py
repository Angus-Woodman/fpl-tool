import datetime as dt

from api.db.session import get_db_session
from api.main import app
from api.routers.imports import get_import_service, get_import_status_store
from api.services.import_fpl_data import ImportSummary
from api.services.import_status import ImportState, ImportStatus, ImportStatusStore
from fastapi.testclient import TestClient


class _FakeService:
    def import_bootstrap_static(self) -> ImportSummary:
        return ImportSummary(
            teams_imported=20,
            players_imported=577,
            gameweeks_imported=38,
            fixtures_imported=380,
        )


class _FakeSession:
    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def test_import_status_defaults_to_idle() -> None:
    status_store = ImportStatusStore(status=ImportStatus(state=ImportState.IDLE))

    app.dependency_overrides[get_import_status_store] = lambda: status_store
    try:
        client = TestClient(app)
        response = client.get("/imports/fpl/status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "idle"
        assert payload["last_summary"] is None
    finally:
        app.dependency_overrides.clear()


def test_import_run_updates_status_and_returns_summary() -> None:
    status_store = ImportStatusStore(status=ImportStatus(state=ImportState.IDLE))

    app.dependency_overrides[get_db_session] = lambda: _FakeSession()
    app.dependency_overrides[get_import_service] = lambda: _FakeService()
    app.dependency_overrides[get_import_status_store] = lambda: status_store
    try:
        client = TestClient(app)
        response = client.post("/imports/fpl/run")

        assert response.status_code == 200
        payload = response.json()
        assert payload["teams_imported"] == 20
        assert payload["fixtures_imported"] == 380

        status_response = client.get("/imports/fpl/status")
        status_payload = status_response.json()

        assert status_payload["state"] == "succeeded"
        assert status_payload["message"] == "Import completed"
        assert status_payload["last_summary"]["players_imported"] == 577

        started_at = dt.datetime.fromisoformat(
            status_payload["last_run_started_at"].replace("Z", "+00:00")
        )
        finished_at = dt.datetime.fromisoformat(
            status_payload["last_run_finished_at"].replace("Z", "+00:00")
        )
        assert finished_at >= started_at
    finally:
        app.dependency_overrides.clear()
