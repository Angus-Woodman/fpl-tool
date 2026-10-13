import datetime as dt

from fpl_engine.domain import Player, PlayerPosition, PlayerSnapshot, Team


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


def test_player_selectability_flags_are_optional_and_default_to_unknown() -> None:
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

    assert player.can_select is None
    assert player.can_transact is None


def test_player_carries_explicit_selectability_flags() -> None:
    player = Player(
        id=1,
        external_fpl_id=101,
        first_name="A",
        second_name="B",
        web_name="AB",
        team_id=1,
        position=PlayerPosition.MIDFIELDER,
        current_price=7.5,
        status="u",
        can_select=False,
        can_transact=True,
    )

    assert player.can_select is False
    assert player.can_transact is True


def test_team_entity_shape() -> None:
    team = Team(id=1, name="Arsenal", short_name="ARS", external_fpl_id=1, source_difficulty=4)

    assert team.short_name == "ARS"
    assert team.source_difficulty == 4
    assert team.strength_overall_home is None


def test_player_snapshot_reported_totals_default_to_zero() -> None:
    snapshot = PlayerSnapshot(
        player_id=1,
        captured_at=dt.datetime(2026, 8, 13, tzinfo=dt.UTC),
        gameweek_id=None,
        price=10.5,
        ownership_percent=31.4,
        transfers_in=0,
        transfers_out=0,
        status="a",
        chance_of_playing_next_round=None,
    )

    assert snapshot.total_minutes == 0
    assert snapshot.total_points == 0
    assert snapshot.points_per_game == 0.0
    assert snapshot.expected_goals is None
