
from fpl_engine.domain import Player, PlayerPosition, Team


def test_player_position_is_strongly_typed_enum() -> None:
    player = Player(
        id=1,
        external_fpl_id=101,
        first_name="A",
        second_name="B",
        web_name="AB",
        team_id=1,
        position=PlayerPosition.MIDFIELDER,
        current_price=7.5,
        status="a",
    )

    assert player.position is PlayerPosition.MIDFIELDER


def test_team_entity_shape() -> None:
    team = Team(id=1, name="Arsenal", short_name="ARS", external_fpl_id=1)

    assert team.short_name == "ARS"
