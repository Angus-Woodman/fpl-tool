import datetime as dt

from api.adapters.fpl.mappers import PlayerSeed, map_bootstrap_static
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


def _element(player_id: int, **extra: object) -> dict[str, object]:
    return {
        "id": player_id,
        "first_name": "First",
        "second_name": "Second",
        "web_name": f"Player{player_id}",
        "team": 1,
        "element_type": 3,
        "now_cost": 50,
        **extra,
    }


def _map_elements(elements: list[dict[str, object]]) -> list[PlayerSeed]:
    dto = BootstrapStaticDto.model_validate(
        {
            "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
            "elements": elements,
            "events": [],
        }
    )
    return map_bootstrap_static(dto).players


def test_bootstrap_mapper_carries_selectability_flags_into_the_player_seed() -> None:
    players = _map_elements(
        [
            _element(1, status="a", can_select=True, can_transact=True),
            _element(2, status="a", can_select=False, can_transact=False),
            _element(3, status="a"),
        ]
    )

    assert [(p.can_select, p.can_transact) for p in players] == [
        (True, True),
        (False, False),
        (None, None),
    ]


def test_bootstrap_mapper_keeps_selectability_independent_of_status() -> None:
    players = _map_elements(
        [
            _element(1, status="a", can_select=False, can_transact=True),
            _element(2, status="i", can_select=True, can_transact=True),
            _element(3, status="u", can_select=False, can_transact=True),
        ]
    )

    assert [(p.status, p.can_select, p.can_transact) for p in players] == [
        ("a", False, True),
        ("i", True, True),
        ("u", False, True),
    ]
