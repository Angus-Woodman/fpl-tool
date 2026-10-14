from __future__ import annotations

from api.services.plan_accounting import (
    PlanGameweekState,
    apply_transfers_forward,
    pair_transfers,
    recalculate_accounting,
)
from builders import POSITIONS, PRICES, build_squad, transfer
from fpl_engine.rules import Chip


def _state(gameweek_number: int, players: list, chip: Chip | None = None) -> PlanGameweekState:
    return PlanGameweekState(gameweek_number=gameweek_number, chip=chip, players=tuple(players))


def _recalculate(states: list[PlanGameweekState], *, bank: float = 0.5, free_transfers: int = 1):
    return recalculate_accounting(
        states,
        initial_bank=bank,
        initial_free_transfers=free_transfers,
        prices=PRICES,
    )


class TestRecalculateAccounting:
    def test_first_gameweek_uses_the_plan_starting_position(self) -> None:
        result = _recalculate([_state(1, build_squad())])

        assert result[0].bank == 0.5
        assert result[0].free_transfers_available == 1
        assert result[0].transfers_made == 0
        assert result[0].points_hit == 0

    def test_unused_transfers_accumulate_from_gameweek_two(self) -> None:
        squad = build_squad()
        result = _recalculate([_state(number, squad) for number in range(1, 8)])

        assert [entry.free_transfers_available for entry in result] == [1, 1, 2, 3, 4, 5, 5]

    def test_gameweek_one_transfers_are_free(self) -> None:
        squad = build_squad()
        after = transfer(transfer(squad, out_id=12, in_id=16), out_id=11, in_id=17)
        result = _recalculate([_state(1, after)], free_transfers=0)

        assert result[0].points_hit == 0

    def test_plans_starting_later_keep_their_banked_transfers(self) -> None:
        squad = build_squad()
        result = _recalculate([_state(number, squad) for number in range(6, 9)], free_transfers=2)

        assert [entry.free_transfers_available for entry in result] == [2, 3, 4]

    def test_transfer_is_detected_and_priced(self) -> None:
        squad = build_squad()
        after = transfer(squad, out_id=12, in_id=16)
        result = _recalculate([_state(1, squad), _state(2, after)])

        assert result[1].transfers_made == 1
        assert result[1].players_out == (12,)
        assert result[1].players_in == (16,)
        assert result[1].bank == 0.5 + PRICES[12] - PRICES[16]

    def test_extra_transfers_cost_four_points_each(self) -> None:
        squad = build_squad()
        after = transfer(
            transfer(transfer(squad, out_id=12, in_id=16), out_id=11, in_id=17),
            out_id=10,
            in_id=20,
        )
        result = _recalculate([_state(1, squad), _state(2, after)])

        assert result[1].free_transfers_available == 1
        assert result[1].transfers_made == 3
        assert result[1].points_hit == 8

    def test_wildcard_gameweek_costs_nothing_and_preserves_transfers(self) -> None:
        squad = build_squad()
        after = transfer(
            transfer(transfer(squad, out_id=12, in_id=16), out_id=11, in_id=17),
            out_id=10,
            in_id=20,
        )
        result = _recalculate([_state(1, squad), _state(2, after, Chip.WILDCARD), _state(3, after)])

        assert result[1].points_hit == 0
        assert result[2].free_transfers_available == 1

    def test_free_hit_squad_reverts_the_following_gameweek(self) -> None:
        squad = build_squad()
        free_hit_squad = transfer(squad, out_id=12, in_id=16)
        result = _recalculate(
            [
                _state(1, squad),
                _state(2, free_hit_squad, Chip.FREE_HIT),
                _state(3, squad),
            ]
        )

        assert result[1].transfers_made == 1
        assert result[2].transfers_made == 0
        assert result[2].bank == 0.5


class TestPairTransfers:
    def test_pairs_by_position_when_possible(self) -> None:
        pairs = pair_transfers([12, 14], [18, 16], POSITIONS)

        assert pairs == {12: 16, 14: 18}

    def test_falls_back_when_positions_do_not_match(self) -> None:
        pairs = pair_transfers([12], [18], POSITIONS)

        assert pairs == {12: 18}


class TestApplyTransfersForward:
    def test_later_gameweeks_inherit_the_transfer(self) -> None:
        squad = build_squad()
        states = [_state(number, squad) for number in range(1, 4)]

        updated = apply_transfers_forward(states, from_index=0, pairs={12: 16})

        assert all(16 in state.player_ids for state in updated[1:])
        assert all(12 not in state.player_ids for state in updated[1:])

    def test_earlier_gameweeks_are_untouched(self) -> None:
        squad = build_squad()
        states = [_state(number, squad) for number in range(1, 4)]

        updated = apply_transfers_forward(states, from_index=1, pairs={12: 16})

        assert 12 in updated[0].player_ids
        assert 16 not in updated[0].player_ids

    def test_gameweek_that_already_moved_the_player_on_is_left_alone(self) -> None:
        squad = build_squad()
        later = transfer(squad, out_id=12, in_id=17)
        states = [_state(1, squad), _state(2, later)]

        updated = apply_transfers_forward(states, from_index=0, pairs={12: 16})

        assert 17 in updated[1].player_ids
        assert 16 not in updated[1].player_ids
