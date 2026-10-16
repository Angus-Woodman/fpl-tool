from __future__ import annotations

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers import (
    SingleTransferEvaluation,
    TransferPlayer,
    evaluate_single_transfer,
)

GK = PlayerPosition.GOALKEEPER
DEF = PlayerPosition.DEFENDER
MID = PlayerPosition.MIDFIELDER
FWD = PlayerPosition.FORWARD


def _player(
    player_id: int,
    position: PlayerPosition,
    *,
    team_id: int | None = None,
    price: float = 5.0,
    projected_points: float = 2.0,
) -> TransferPlayer:
    return TransferPlayer(
        player_id=player_id,
        position=position,
        team_id=team_id if team_id is not None else player_id,
        price=price,
        projected_points=projected_points,
    )


def _squad() -> list[TransferPlayer]:
    return [
        _player(1, GK, team_id=101, price=4.5, projected_points=3.6),
        _player(2, GK, team_id=102, price=4.0, projected_points=2.0),
        _player(3, DEF, team_id=103, price=5.0, projected_points=3.0),
        _player(4, DEF, team_id=104, price=4.8, projected_points=2.8),
        _player(5, DEF, team_id=105, price=4.5, projected_points=2.5),
        _player(6, DEF, team_id=106, price=4.0, projected_points=1.0),
        _player(7, DEF, team_id=107, price=4.0, projected_points=0.5),
        _player(8, MID, team_id=108, price=8.0, projected_points=3.5),
        _player(9, MID, team_id=109, price=7.0, projected_points=3.3),
        _player(10, MID, team_id=110, price=6.0, projected_points=2.9),
        _player(11, MID, team_id=111, price=4.5, projected_points=0.2),
        _player(12, MID, team_id=112, price=4.0, projected_points=0.1),
        _player(13, FWD, team_id=113, price=12.0, projected_points=4.5),
        _player(14, FWD, team_id=114, price=9.0, projected_points=4.0),
        _player(15, FWD, team_id=115, price=5.0, projected_points=3.8),
    ]


def _run(
    squad: list[TransferPlayer], player_out_id: int, player_in: TransferPlayer, bank: float
) -> SingleTransferEvaluation:
    return evaluate_single_transfer(
        squad=squad, player_out_id=player_out_id, player_in=player_in, bank=bank
    )


class TestLegalTransfer:
    def test_a_legal_same_position_affordable_swap_is_legal(self) -> None:
        incoming = _player(16, MID, team_id=116, price=4.5, projected_points=2.8)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert result.is_legal is True
        assert result.errors == ()

    def test_squad_after_replaces_the_outgoing_player_with_the_incoming_one(self) -> None:
        incoming = _player(16, MID, team_id=116, price=4.5, projected_points=2.8)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert 11 not in result.squad_after
        assert 16 in result.squad_after
        assert len(result.squad_after) == 15

    def test_resulting_bank_accounts_for_the_price_difference(self) -> None:
        incoming = _player(16, MID, team_id=116, price=5.5, projected_points=2.8)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=2.0)

        # outgoing player 11 sells for 4.5; incoming costs 5.5.
        assert result.resulting_bank == pytest.approx(2.0 + 4.5 - 5.5)

    def test_projected_team_gain_uses_the_optimal_xi_before_and_after_not_the_squad(
        self,
    ) -> None:
        # Player 11 (0.2 xPts) is already benched in the optimal XI, so a
        # replacement with modest points may not change the optimal XI's
        # captain-adjusted total by the full direct difference.
        incoming = _player(16, MID, team_id=116, price=4.5, projected_points=0.6)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert result.optimal_xi_before is not None
        assert result.optimal_xi_after is not None
        expected_gain = (
            result.optimal_xi_after.captain_adjusted_points
            - result.optimal_xi_before.captain_adjusted_points
        )
        assert result.projected_team_gain == pytest.approx(expected_gain)

    def test_direct_player_xpts_difference_is_a_separate_explanatory_metric(self) -> None:
        incoming = _player(16, MID, team_id=116, price=4.5, projected_points=0.6)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert result.direct_player_xpts_difference == pytest.approx(0.6 - 0.2)
        # The primary metric is the team-level gain, not the naive diff --
        # for a bench-only upgrade these two values need not be equal.
        assert result.direct_player_xpts_difference != result.projected_team_gain


class TestIllegalTransfers:
    def test_outgoing_player_not_in_squad_is_illegal(self) -> None:
        incoming = _player(16, MID, team_id=116, price=4.5, projected_points=2.8)

        result = _run(_squad(), player_out_id=999, player_in=incoming, bank=0.0)

        assert result.is_legal is False
        assert "player_not_in_squad" in result.errors
        assert result.squad_after == result.squad_before
        assert result.optimal_xi_after is None

    def test_incoming_player_already_in_squad_is_illegal(self) -> None:
        incoming = _player(9, MID, team_id=109, price=7.0, projected_points=3.3)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert result.is_legal is False
        assert "player_already_in_squad" in result.errors

    def test_mismatched_position_swap_is_illegal(self) -> None:
        incoming = _player(16, FWD, team_id=116, price=4.5, projected_points=2.8)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert result.is_legal is False
        assert "invalid_position_composition" in result.errors
        assert result.optimal_xi_after is None
        assert result.projected_team_gain == 0.0

    def test_exceeding_the_max_players_per_club_is_illegal(self) -> None:
        # Team 108 already fields midfielder 8; adding two more from the same
        # club would exceed the 3-per-club limit.
        squad = _squad()
        squad[9] = _player(10, MID, team_id=108, price=6.0, projected_points=2.9)
        squad[10] = _player(11, MID, team_id=108, price=4.5, projected_points=0.2)
        incoming = _player(16, MID, team_id=108, price=4.5, projected_points=2.8)

        result = _run(squad, player_out_id=12, player_in=incoming, bank=0.0)

        assert result.is_legal is False
        assert "club_limit_exceeded" in result.errors
        # Position composition is still valid, so the optimal XI can still be
        # computed for information even though the transfer itself is illegal.
        assert result.optimal_xi_after is not None

    def test_insufficient_bank_is_illegal(self) -> None:
        incoming = _player(16, MID, team_id=116, price=20.0, projected_points=2.8)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.0)

        assert result.is_legal is False
        assert "insufficient_bank" in result.errors
        assert result.resulting_bank < 0
        assert result.optimal_xi_after is not None


class TestDeterminism:
    def test_identical_inputs_produce_an_identical_result(self) -> None:
        squad = _squad()
        incoming = _player(16, MID, team_id=116, price=4.5, projected_points=2.8)

        first = _run(squad, 11, incoming, 0.0)
        second = _run(squad, 11, incoming, 0.0)

        assert first == second


class TestExactBankArithmetic:
    def test_the_float_formula_would_have_drifted_for_this_case(self) -> None:
        assert 1.2 + 5.9 - 6.6 != 0.5

    def test_resulting_bank_is_an_exact_tenth(self) -> None:
        squad = [
            _player(
                p.player_id,
                p.position,
                team_id=p.team_id,
                price=5.9 if p.player_id == 11 else p.price,
            )
            for p in _squad()
        ]
        incoming = _player(16, MID, team_id=116, price=6.6)

        result = _run(squad, player_out_id=11, player_in=incoming, bank=1.2)

        assert result.resulting_bank == 0.5
        assert repr(result.resulting_bank) == "0.5"

    def test_a_chain_of_transfers_never_accumulates_noise(self) -> None:
        import random
        from decimal import Decimal

        rng = random.Random(1)
        bank = 0.5
        expected_tenths = 5
        for _ in range(300):
            incoming_tenths = rng.randint(39, 145)
            incoming = _player(16, MID, team_id=116, price=incoming_tenths / 10)
            bank = _run(_squad(), player_out_id=11, player_in=incoming, bank=bank).resulting_bank
            expected_tenths += 45 - incoming_tenths
            assert Decimal(str(bank)) * 10 == expected_tenths

    def test_a_drifted_stored_bank_is_normalised_in_the_result(self) -> None:
        incoming = _player(16, MID, team_id=116, price=4.5)

        result = _run(_squad(), player_out_id=11, player_in=incoming, bank=0.5000000000000062)

        assert result.resulting_bank == 0.5
        assert repr(result.resulting_bank) == "0.5"
        assert result.is_legal is True

    @pytest.mark.parametrize("bank", [0.55, 0.05, float("nan"), float("inf"), 1e308])
    def test_an_invalid_bank_is_rejected_not_rounded(self, bank: float) -> None:
        incoming = _player(16, MID, team_id=116, price=4.5)

        with pytest.raises(RuleViolationError) as error:
            _run(_squad(), player_out_id=11, player_in=incoming, bank=bank)

        assert error.value.code == "invalid_money"

    @pytest.mark.parametrize("price", [4.55, 0.5000000000000062, float("nan")])
    def test_an_invalid_incoming_price_is_rejected_not_rounded(self, price: float) -> None:
        incoming = _player(16, MID, team_id=116, price=price)

        with pytest.raises(RuleViolationError) as error:
            _run(_squad(), player_out_id=11, player_in=incoming, bank=1.0)

        assert error.value.code == "invalid_money"

    def test_an_invalid_outgoing_price_is_rejected_not_rounded(self) -> None:
        squad = [
            _player(
                p.player_id,
                p.position,
                team_id=p.team_id,
                price=4.55 if p.player_id == 11 else p.price,
            )
            for p in _squad()
        ]
        incoming = _player(16, MID, team_id=116, price=4.5)

        with pytest.raises(RuleViolationError) as error:
            _run(squad, player_out_id=11, player_in=incoming, bank=1.0)

        assert error.value.code == "invalid_money"
