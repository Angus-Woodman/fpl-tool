"""Guarded real-API browser journeys for the Planner Transfer Explorer.

Each journey serves the real API on an isolated schema of the dedicated test
database and drives the Explorer in a real browser (Playwright) against a
frontend whose address is given by ``PLANNER_BASE_URL``. The browser then reloads
the plan, and this test re-reads the database, so a transfer is only counted as
saved when it is actually persisted. Nothing here touches the development
database or the user's running servers.
"""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path
from threading import Thread

import httpx
import pytest
import uvicorn
from api.db.session import get_db_session
from api.main import app
from api.models import PlayerModel
from api.repositories.plan_repository import PlanRepository
from conftest import requires_database
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_plan_transfer_explorer_integration import seed_plan_and_projections

pytestmark = [
    requires_database,
    pytest.mark.skipif(
        os.getenv("RUN_PLANNER_BROWSER_TESTS") != "1",
        reason="Requires installed Playwright and a frontend at PLANNER_BASE_URL",
    ),
]

GREP = {
    "confirm": "US2 real API confirm persists",
    "prices": "US2 real API prices changed",
    "not_saved": "US2 real API accepted-but-not-saved",
}


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("journey", ["confirm", "prices", "not_saved"])
def test_explorer_journey_persists_through_actual_browser_and_api(
    planner_session,
    planner_plan,
    planner_metadata,
    journey,
    width,
    tmp_path,
    monkeypatch,
):
    base_url = os.environ.get("PLANNER_BASE_URL")
    assert (
        base_url and base_url != "http://127.0.0.1:3000"
    ), "Set PLANNER_BASE_URL to an isolated preview, never the user's dev server on 3000"
    plan_id = seed_plan_and_projections(planner_session, planner_plan, planner_metadata)
    engine = planner_session.get_bind()
    price_file = tmp_path / "incoming-price-change"
    fault_file = tmp_path / "canonical-write-fault"

    def request_session() -> Iterator[Session]:
        # One-shot trigger: the browser creates the file between preview and confirm.
        if price_file.exists():
            price_file.unlink()
            with Session(engine) as writer:
                writer.get(PlayerModel, 106).current_price = 5.4
                writer.commit()
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = request_session
    real_save = PlanRepository.save_canonical

    def save_unless_faulted(*args, **kwargs):
        if fault_file.exists():
            raise SQLAlchemyError("Injected canonical write failure after receipt")
        return real_save(*args, **kwargs)

    monkeypatch.setattr(PlanRepository, "save_canonical", save_unless_faulted)

    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
            thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                assert httpx.get(f"http://127.0.0.1:{port}/plans/{plan_id}").status_code == 200
                result = subprocess.run(
                    [
                        "pnpm",
                        "--filter",
                        "web",
                        "e2e",
                        "tests/e2e/planner-transfer-workflow.spec.ts",
                        "--grep",
                        GREP[journey],
                        "--workers=1",
                        "--reporter=line",
                    ],
                    cwd=Path(__file__).parents[4],
                    env={
                        **os.environ,
                        "PLANNER_TEST_API_URL": f"http://127.0.0.1:{port}",
                        "PLANNER_TEST_PLAN_ID": str(plan_id),
                        "PLANNER_TEST_GAMEWEEK": "8",
                        "PLANNER_VIEWPORT": str(width),
                        "PLANNER_PRICE_FILE": str(price_file),
                        "PLANNER_FAULT_FILE": str(fault_file),
                    },
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                assert result.returncode == 0, result.stdout + result.stderr
                assert "1 passed" in result.stdout, result.stdout
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                assert not thread.is_alive()
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    # The browser's own reads are not trusted: the database is read again here.
    planner_session.expire_all()
    reopened = PlanRepository(planner_session).load_canonical(plan_id)
    transfers = [
        (week.gameweek_number, transfer.outgoing_player_id, transfer.incoming_player_id)
        for week in reopened.gameweeks
        for transfer in week.transfers
    ]
    assert transfers == [(8, 6, 106)]
    assert reopened.revision == 1
    assert not fault_file.exists()
