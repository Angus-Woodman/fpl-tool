from __future__ import annotations

import os
import statistics
import time
from collections.abc import Iterator

import pytest
from api.db.session import get_db_session
from api.main import app
from conftest import requires_database
from fastapi.testclient import TestClient
from perf_dataset import add_long_plan, build_dataset
from sqlalchemy.orm import Session

pytestmark = [
    requires_database,
    pytest.mark.skipif(
        os.getenv("RUN_PERF_TESTS") != "1", reason="Set RUN_PERF_TESTS=1 to run the timing gate."
    ),
]

LIST_BUDGET_SECONDS = 3.0
RUNS = 12  # the first is discarded as warm-up


@pytest.fixture
def client(planner_session: Session) -> Iterator[TestClient]:
    engine = planner_session.get_bind()

    def request_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = request_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def timed(client: TestClient, url: str, runs: int = RUNS) -> list[float]:
    timings: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        response = client.get(url)
        timings.append(time.perf_counter() - started)
        assert response.status_code == 200, response.text
    return timings[1:]


def test_listing_a_full_season_midfielder_pool_stays_within_the_budget(
    client: TestClient, planner_session: Session
) -> None:
    dataset = build_dataset(planner_session)
    url = f"/plans/{dataset.plan_id}/gameweeks/8/transfers/{dataset.midfielder_in_squad}"
    payload = client.get(url).json()
    pool = len(payload["candidates"])

    timings = timed(client, url)
    median, worst = statistics.median(timings), max(timings)
    print(
        f"\nPERF list: 8-gameweek plan, pool={pool}, runs={len(timings)}, "
        f"median={median:.3f}s, worst={worst:.3f}s"
    )
    assert pool >= 200
    assert median <= LIST_BUDGET_SECONDS

    long_plan = add_long_plan(planner_session, dataset, 31)
    long_url = f"/plans/{long_plan}/gameweeks/8/transfers/{dataset.midfielder_in_squad}"
    long_timings = timed(client, long_url, runs=4)
    print(
        f"PERF list: 31-gameweek plan (reported, not gating), "
        f"median={statistics.median(long_timings):.3f}s, worst={max(long_timings):.3f}s"
    )


PREVIEW_BUDGET_SECONDS = 2.0


def test_previewing_one_candidate_stays_within_the_budget(
    client: TestClient, planner_session: Session
) -> None:
    dataset = build_dataset(planner_session)
    listing = client.get(
        f"/plans/{dataset.plan_id}/gameweeks/8/transfers/{dataset.midfielder_in_squad}"
    ).json()
    candidate = next(item for item in listing["candidates"] if item["state"] == "available")
    url = (
        f"/plans/{dataset.plan_id}/gameweeks/8/transfers/{dataset.midfielder_in_squad}"
        f"/preview?player_in_id={candidate['player_id']}"
    )

    timings = timed(client, url)
    median, worst = statistics.median(timings), max(timings)
    print(
        f"\nPERF preview: 8-gameweek plan, runs={len(timings)}, "
        f"median={median:.3f}s, worst={worst:.3f}s"
    )
    assert median <= PREVIEW_BUDGET_SECONDS
