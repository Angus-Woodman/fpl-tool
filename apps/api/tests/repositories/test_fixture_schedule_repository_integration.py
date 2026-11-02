from __future__ import annotations

import datetime as dt

from api.models import FixtureModel, GameweekModel, TeamModel
from api.repositories.fixture_read_repository import FixtureReadRepository
from conftest import requires_database
from sqlalchemy.orm import Session

pytestmark = requires_database


def _seed(session: Session) -> dict[str, int]:
    teams = [
        TeamModel(external_fpl_id=n, name=f"Club {n}", short_name=f"C{n}", source_difficulty=3)
        for n in range(1, 4)
    ]
    session.add_all(teams)
    session.flush()
    weeks = {}
    for number in (7, 8, 9, 10, 12):
        week = GameweekModel(
            number=number,
            name=f"Gameweek {number}",
            deadline=dt.datetime(2026, 10, 1, tzinfo=dt.UTC) + dt.timedelta(days=number),
            is_current=False,
            is_next=False,
            is_finished=False,
        )
        session.add(week)
        weeks[number] = week
    session.flush()
    kickoff = dt.datetime(2026, 10, 20, 15, tzinfo=dt.UTC)

    def fixture(external: int, week: int | None, home: int, away: int, finished: bool) -> int:
        row = FixtureModel(
            external_fpl_id=external,
            gameweek_id=weeks[week].id if week is not None else None,
            home_team_id=teams[home].id,
            away_team_id=teams[away].id,
            kickoff_time=kickoff,
            finished=finished,
        )
        session.add(row)
        session.flush()
        return row.id

    return {
        "before_range": fixture(1, 7, 0, 1, False),
        "gw8": fixture(2, 8, 0, 1, False),
        "gw9_first": fixture(3, 9, 0, 1, False),
        "gw9_second": fixture(4, 9, 2, 0, False),
        "gw10_finished": fixture(5, 10, 1, 2, True),
        "after_range": fixture(6, 12, 0, 1, False),
        "postponed": fixture(7, None, 1, 2, False),
        "old_unscheduled_finished": fixture(8, None, 0, 2, True),
    }


def test_schedule_returns_the_range_and_unfinished_unscheduled_fixtures(
    planner_session: Session,
) -> None:
    ids = _seed(planner_session)

    schedule = FixtureReadRepository(planner_session).list_schedule(min_gameweek=8, max_gameweek=10)

    by_id = {item.fixture_id: item for item in schedule}
    assert set(by_id) == {
        ids["gw8"],
        ids["gw9_first"],
        ids["gw9_second"],
        ids["gw10_finished"],
        ids["postponed"],
    }
    assert by_id[ids["postponed"]].gameweek_number is None
    assert by_id[ids["gw10_finished"]].finished is True
    assert by_id[ids["gw9_second"]].gameweek_number == 9


def test_a_club_with_two_fixtures_in_a_gameweek_has_both_records(
    planner_session: Session,
) -> None:
    ids = _seed(planner_session)
    schedule = FixtureReadRepository(planner_session).list_schedule(min_gameweek=9, max_gameweek=9)

    second = next(item for item in schedule if item.fixture_id == ids["gw9_second"])
    first = next(item for item in schedule if item.fixture_id == ids["gw9_first"])
    assert first.home_team_id == second.away_team_id  # the same club plays both
