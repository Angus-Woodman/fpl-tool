import datetime as dt

from api.adapters.fpl.mappers import map_fixtures
from api.adapters.fpl.schemas import FplFixtureDto


def test_fixture_mapper_converts_external_fixture_payload() -> None:
    fixtures = [
        FplFixtureDto.model_validate(
            {
                "id": 9001,
                "event": 2,
                "team_h": 1,
                "team_a": 2,
                "kickoff_time": "2026-08-21T18:30:00Z",
                "team_h_score": None,
                "team_a_score": None,
                "finished": False,
            }
        )
    ]

    mapped = map_fixtures(fixtures)

    assert mapped[0].external_fpl_id == 9001
    assert mapped[0].gameweek_number == 2
    assert mapped[0].home_team_external_fpl_id == 1
    assert mapped[0].away_team_external_fpl_id == 2
    assert mapped[0].kickoff_time == dt.datetime(2026, 8, 21, 18, 30, tzinfo=dt.UTC)
