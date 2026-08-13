from __future__ import annotations

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers import (
    GameweekProjections,
    PricedPlayer,
    rank_replacement_candidates,
)

GK = PlayerPosition.GOALKEEPER
DEF = PlayerPosition.DEFENDER
MID = PlayerPosition.MIDFIELDER
FWD = PlayerPosition.FORWARD


def _priced(
    player_id: int, position: PlayerPosition, *, team_id: int | None = None, price: float = 5.0
) -> PricedPlayer:
    return PricedPlayer(
        player_id=player_id,
        position=position,
        team_id=team_id if team_id is not None else player_id,
        price=price,
    )


def _squad() -> list[PricedPlayer]:
    return [
        _priced(1, GK, team_id=101, price=4.5),
        _priced(2, GK, team_id=102, price=4.0),
        _priced(3, DEF, team_id=103, price=5.0),
        _priced(4, DEF, team_id=104, price=4.8),
        _priced(5, DEF, team_id=105, price=4.5),
        _priced(6, DEF, team_id=106, price=4.0),
        _priced(7, DEF, team_id=107, price=4.0),
        _priced(8, MID, team_id=108, price=8.0),
        _priced(9, MID, team_id=109, price=7.0),
        _priced(10, MID, team_id=110, price=6.0),
        _priced(11, MID, team_id=111, price=4.5),
        _priced(12, MID, team_id=112, price=4.0),
        _priced(13, FWD, team_id=113, price=12.0),
        _priced(14, FWD, team_id=114, price=9.0),
        _priced(15, FWD, team_id=115, price=5.0),
    ]


def _base_points() -> dict[int, float]:
    """A fixed, plausible projection for the squad, held constant across all
    test gameweeks unless a test overrides a specific player/gameweek."""
    return {
        1: 3.6,
        2: 2.0,
        3: 3.0,
        4: 2.8,
        5: 2.5,
        6: 1.0,
        7: 0.5,
        8: 3.5,
        9: 3.3,
        10: 2.9,
        11: 0.2,
        12: 0.1,
        13: 4.5,
        14: 4.0,
        15: 3.8,
    }


def _gameweeks(
    count: int, *, overrides: dict[int, dict[int, float]] | None = None
) -> list[GameweekProjections]:
    overrides = overrides or {}
    result = []
    for index in range(count):
        gameweek_number = index + 1
        points = {**_base_points(), **overrides.get(gameweek_number, {})}
        result.append(
            GameweekProjections(gameweek_number=gameweek_number, projected_points_by_player=points)
        )
    return result


class TestCandidateFiltering:
    def test_only_same_position_candidates_are_considered(self) -> None:
        candidates = [
            _priced(20, FWD, team_id=120, price=4.5),  # wrong position for a MID transfer
            _priced(21, MID, team_id=121, price=4.5),
        ]
        gameweeks = _gameweeks(1, overrides={1: {20: 5.0, 21: 3.0}})

        results = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1,),
            primary_horizon=1,
        )

        assert {result.candidate_player_id for result in results} == {21}

    def test_candidates_already_in_the_squad_are_excluded(self) -> None:
        candidates = [_priced(9, MID, team_id=109, price=7.0)]  # already owned
        gameweeks = _gameweeks(1)

        results = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1,),
            primary_horizon=1,
        )

        assert results == []

    def test_unaffordable_candidates_are_excluded(self) -> None:
        candidates = [_priced(21, MID, team_id=121, price=50.0)]
        gameweeks = _gameweeks(1)

        results = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1,),
            primary_horizon=1,
        )

        assert results == []

    def test_club_limit_violating_candidates_are_excluded(self) -> None:
        squad = _squad()
        squad[9] = _priced(10, MID, team_id=108, price=6.0)
        squad[10] = _priced(11, MID, team_id=108, price=4.5)
        candidates = [_priced(21, MID, team_id=108, price=4.5)]
        gameweeks = _gameweeks(1)

        results = rank_replacement_candidates(
            squad=squad,
            player_out_id=12,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1,),
            primary_horizon=1,
        )

        assert results == []

    def test_raises_when_the_outgoing_player_is_not_in_the_squad(self) -> None:
        with pytest.raises(RuleViolationError) as error:
            rank_replacement_candidates(
                squad=_squad(),
                player_out_id=999,
                candidates=[_priced(21, MID, team_id=121, price=4.5)],
                bank=0.0,
                gameweek_projections=_gameweeks(1),
                horizons=(1,),
                primary_horizon=1,
            )
        assert error.value.code == "player_not_in_squad"


class TestHorizonAggregation:
    def test_team_gain_is_summed_across_the_full_horizon(self) -> None:
        # Midfielder 21 (a clear upgrade on bench-warmer 11) projects the same
        # improvement in every gameweek, so a 3-GW total should be roughly 3x
        # a single gameweek's gain.
        candidates = [_priced(21, MID, team_id=121, price=4.5)]
        overrides = {gw: {21: 3.0} for gw in (1, 2, 3)}
        one_gw = _gameweeks(1, overrides=overrides)
        three_gw = _gameweeks(3, overrides=overrides)

        [one_gw_result] = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=one_gw,
            horizons=(1,),
            primary_horizon=1,
        )
        [three_gw_result] = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=three_gw,
            horizons=(1, 3),
            primary_horizon=3,
        )

        assert three_gw_result.team_gain_by_horizon[1] == pytest.approx(
            one_gw_result.team_gain_by_horizon[1]
        )
        assert three_gw_result.team_gain_by_horizon[3] == pytest.approx(
            3 * one_gw_result.team_gain_by_horizon[1]
        )

    def test_horizon_beyond_available_gameweeks_uses_only_what_is_available(self) -> None:
        candidates = [_priced(21, MID, team_id=121, price=4.5)]
        overrides = {gw: {21: 3.0} for gw in (1, 2)}
        gameweeks = _gameweeks(2, overrides=overrides)

        [result] = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1, 3, 5),
            primary_horizon=5,
        )

        assert result.gameweeks_evaluated == 2
        # A 5-GW request with only 2 gameweeks of data honestly reports the
        # 2-gameweek total, not a fabricated 5-gameweek figure.
        assert result.team_gain_by_horizon[5] == pytest.approx(result.team_gain_by_horizon[3])
        assert result.team_gain_by_horizon[3] > result.team_gain_by_horizon[1]

    def test_resulting_bank_is_constant_across_the_horizon(self) -> None:
        candidates = [_priced(21, MID, team_id=121, price=5.0)]
        gameweeks = _gameweeks(3)

        [result] = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=1.0,
            gameweek_projections=gameweeks,
            horizons=(1, 3),
            primary_horizon=3,
        )

        assert result.resulting_bank == pytest.approx(1.0 + 4.5 - 5.0)


class TestRanking:
    def test_results_are_ranked_by_the_primary_horizon_descending(self) -> None:
        candidates = [
            _priced(21, MID, team_id=121, price=4.5),
            _priced(22, MID, team_id=122, price=4.5),
        ]
        gameweeks = _gameweeks(1, overrides={1: {21: 1.0, 22: 3.0}})

        results = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1,),
            primary_horizon=1,
        )

        assert [result.candidate_player_id for result in results] == [22, 21]

    def test_tied_candidates_resolve_to_the_lower_player_id(self) -> None:
        candidates = [
            _priced(22, MID, team_id=122, price=4.5),
            _priced(21, MID, team_id=121, price=4.5),
        ]
        gameweeks = _gameweeks(1, overrides={1: {21: 3.0, 22: 3.0}})

        results = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1,),
            primary_horizon=1,
        )

        assert [result.candidate_player_id for result in results] == [21, 22]


class TestDeterminism:
    def test_identical_inputs_produce_an_identical_result(self) -> None:
        candidates = [_priced(21, MID, team_id=121, price=4.5)]
        gameweeks = _gameweeks(3)

        first = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1, 3, 5),
            primary_horizon=3,
        )
        second = rank_replacement_candidates(
            squad=_squad(),
            player_out_id=11,
            candidates=candidates,
            bank=0.0,
            gameweek_projections=gameweeks,
            horizons=(1, 3, 5),
            primary_horizon=3,
        )

        assert first == second
