import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers import (
    PricedPlayer,
    candidate_pool_exclusion,
    incoming_selectability_exclusion,
)

OUTGOING_ID = 1


def _squad() -> list[PricedPlayer]:
    return [
        PricedPlayer(
            player_id=OUTGOING_ID, position=PlayerPosition.MIDFIELDER, team_id=1, price=7.0
        ),
        PricedPlayer(player_id=2, position=PlayerPosition.MIDFIELDER, team_id=2, price=6.0),
        PricedPlayer(player_id=3, position=PlayerPosition.FORWARD, team_id=3, price=8.0),
    ]


def _candidate(
    *,
    player_id: int = 50,
    position: PlayerPosition = PlayerPosition.MIDFIELDER,
    can_select: bool | None = True,
    can_transact: bool | None = True,
) -> PricedPlayer:
    return PricedPlayer(
        player_id=player_id,
        position=position,
        team_id=9,
        price=7.5,
        can_select=can_select,
        can_transact=can_transact,
    )


def test_in_pool_candidate_has_no_exclusion() -> None:
    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, _candidate()) is None


def test_already_owned_candidate_is_excluded() -> None:
    owned = _candidate(player_id=2)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, owned) == "player_already_in_squad"


def test_the_outgoing_player_themselves_counts_as_owned() -> None:
    outgoing = _candidate(player_id=OUTGOING_ID)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, outgoing) == "player_already_in_squad"


def test_different_position_candidate_is_excluded() -> None:
    forward = _candidate(position=PlayerPosition.FORWARD)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, forward) == "different_position"


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(False, True), (True, False), (False, False)],
)
def test_either_flag_false_means_not_selectable(
    can_select: bool | None, can_transact: bool | None
) -> None:
    candidate = _candidate(can_select=can_select, can_transact=can_transact)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, candidate) == "player_not_selectable"


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(None, None), (True, None), (None, True)],
)
def test_missing_flag_without_a_known_false_is_unknown(
    can_select: bool | None, can_transact: bool | None
) -> None:
    candidate = _candidate(can_select=can_select, can_transact=can_transact)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, candidate) == "selectability_unknown"


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(False, None), (None, False)],
)
def test_a_known_false_flag_wins_over_a_missing_other_flag(
    can_select: bool | None, can_transact: bool | None
) -> None:
    candidate = _candidate(can_select=can_select, can_transact=can_transact)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, candidate) == "player_not_selectable"


def test_can_transact_true_does_not_override_can_select_false() -> None:
    # Live data: 105 players with status "u" are can_select=False, can_transact=True.
    candidate = _candidate(can_select=False, can_transact=True)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, candidate) == "player_not_selectable"


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(False, False), (False, None), (None, None), (None, False)],
)
def test_owned_candidate_reports_the_structural_reason_over_any_flag_state(
    can_select: bool | None, can_transact: bool | None
) -> None:
    owned = _candidate(player_id=2, can_select=can_select, can_transact=can_transact)

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, owned) == "player_already_in_squad"


@pytest.mark.parametrize(
    ("can_select", "can_transact"),
    [(False, False), (False, None), (None, None), (None, False)],
)
def test_wrong_position_candidate_reports_the_structural_reason_over_any_flag_state(
    can_select: bool | None, can_transact: bool | None
) -> None:
    forward = _candidate(
        position=PlayerPosition.FORWARD, can_select=can_select, can_transact=can_transact
    )

    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, forward) == "different_position"


def test_owned_is_reported_before_different_position() -> None:
    owned_forward = _candidate(player_id=3, position=PlayerPosition.FORWARD)

    assert (
        candidate_pool_exclusion(_squad(), OUTGOING_ID, owned_forward) == "player_already_in_squad"
    )


def test_outgoing_player_must_be_in_the_squad() -> None:
    with pytest.raises(RuleViolationError) as exc_info:
        candidate_pool_exclusion(_squad(), 999, _candidate())

    assert exc_info.value.code == "player_not_in_squad"


@pytest.mark.parametrize(
    ("can_select", "can_transact", "expected"),
    [
        (True, True, None),
        (False, True, "player_not_selectable"),
        (True, False, "player_not_selectable"),
        (False, False, "player_not_selectable"),
        (False, None, "player_not_selectable"),
        (None, False, "player_not_selectable"),
        (None, None, "selectability_unknown"),
        (True, None, "selectability_unknown"),
        (None, True, "selectability_unknown"),
    ],
)
def test_incoming_selectability_exclusion_matches_pool_precedence(
    can_select: bool | None, can_transact: bool | None, expected: str | None
) -> None:
    assert incoming_selectability_exclusion(can_select, can_transact) == expected
    candidate = _candidate(can_select=can_select, can_transact=can_transact)
    assert candidate_pool_exclusion(_squad(), OUTGOING_ID, candidate) == expected


def test_incoming_selectability_exclusion_takes_no_playing_status_input() -> None:
    import inspect

    assert list(inspect.signature(incoming_selectability_exclusion).parameters) == [
        "can_select",
        "can_transact",
    ]
