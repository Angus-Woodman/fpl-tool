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
