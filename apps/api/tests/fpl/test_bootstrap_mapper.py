import datetime as dt

from api.adapters.fpl.mappers import map_bootstrap_static
from api.adapters.fpl.schemas import BootstrapStaticDto


def test_bootstrap_mapper_converts_price_and_positions() -> None:
    dto = BootstrapStaticDto.model_validate(
        {
            "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
            "elements": [
                {
                    "id": 42,
                    "first_name": "Bukayo",
                    "second_name": "Saka",
                    "web_name": "Saka",
                    "team": 1,
                    "element_type": 3,
                    "now_cost": 105,
                    "status": "a",
                }
            ],
            "events": [
                {
                    "id": 1,
                    "name": "Gameweek 1",
                    "deadline_time": "2026-08-14T18:30:00Z",
                    "is_current": False,
                    "is_next": True,
                    "is_finished": False,
                }
            ],
        }
    )

    mapped = map_bootstrap_static(dto)

    assert mapped.players[0].current_price == 10.5
    assert mapped.players[0].position.value == "MID"
    assert mapped.gameweeks[0].deadline == dt.datetime(2026, 8, 14, 18, 30, tzinfo=dt.UTC)


def test_bootstrap_mapper_derives_team_difficulty_from_strength() -> None:
    dto = BootstrapStaticDto.model_validate(
        {
            "teams": [
                {"id": 1, "name": "Arsenal", "short_name": "ARS", "strength": 5},
                {"id": 2, "name": "Sunderland", "short_name": "SUN", "strength": 2},
                {"id": 3, "name": "Unknown FC", "short_name": "UNK"},
                {"id": 4, "name": "Off Scale", "short_name": "OFF", "strength": 9},
            ],
            "elements": [],
            "events": [],
        }
    )

    mapped = map_bootstrap_static(dto)

    difficulty_by_short_name = {team.short_name: team.source_difficulty for team in mapped.teams}
    assert difficulty_by_short_name["ARS"] == 5
    assert difficulty_by_short_name["SUN"] == 2
    assert difficulty_by_short_name["UNK"] == 3
    assert difficulty_by_short_name["OFF"] == 5
