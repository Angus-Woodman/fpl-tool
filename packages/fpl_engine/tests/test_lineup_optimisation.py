from __future__ import annotations

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.optimisation import LineupCandidate, LineupSelection, optimise_lineup
from fpl_engine.rules import RuleViolationError

GK = PlayerPosition.GOALKEEPER
DEF = PlayerPosition.DEFENDER
MID = PlayerPosition.MIDFIELDER
FWD = PlayerPosition.FORWARD


def _candidate(
    player_id: int, position: PlayerPosition, points: float, *, team_id: int | None = None
) -> LineupCandidate:
    return LineupCandidate(
        player_id=player_id,
        position=position,
        team_id=team_id if team_id is not None else player_id,
        projected_points=points,
    )


def _balanced_squad() -> list[LineupCandidate]:
    """A squad where a plain 4-4-2-ish default is clearly not optimal: two
    forwards project far higher than the weakest midfielders, so the optimum
    formation should favour more forwards over the least productive
    midfielder."""
    return [
        _candidate(1, GK, 3.6),
        _candidate(2, GK, 2.0),
        _candidate(3, DEF, 3.0),
        _candidate(4, DEF, 2.8),
        _candidate(5, DEF, 2.5),
        _candidate(6, DEF, 1.0),
        _candidate(7, DEF, 0.5),
        _candidate(8, MID, 3.5),
        _candidate(9, MID, 3.3),
        _candidate(10, MID, 2.9),
        _candidate(11, MID, 0.2),
        _candidate(12, MID, 0.1),
        _candidate(13, FWD, 4.5),
        _candidate(14, FWD, 4.0),
        _candidate(15, FWD, 3.8),
    ]


def _run(squad: list[LineupCandidate]) -> LineupSelection:
    return optimise_lineup(squad)


class TestFormationSelection:
    def test_selects_the_formation_maximising_total_starting_points(self) -> None:
        result = _run(_balanced_squad())

        # 3 forwards (13,14,15) all outproject the weakest midfielders (11,12),
        # so the optimum formation should start all three forwards and only
        # the top 3 midfielders (8,9,10), i.e. a 4-3-3 rather than a 4-4-2.
        assert set(result.starting_xi) >= {13, 14, 15}
        assert 11 not in result.starting_xi
        assert 12 not in result.starting_xi

    def test_starting_xi_always_has_exactly_one_goalkeeper(self) -> None:
        result = _run(_balanced_squad())

        assert len(result.starting_xi) == 11
        assert 1 in result.starting_xi  # higher-projected GK starts
        assert 2 not in result.starting_xi

    def test_result_satisfies_a_legal_formation(self) -> None:
        # Regression for "reuse existing rules": if the selection logic ever
        # produced an illegal formation, validate_starting_formation (called
        # internally) would already have raised before returning.
        result = _run(_balanced_squad())
        assert len(result.starting_xi) == 11


class TestGoalkeeperHandling:
    def test_higher_projected_goalkeeper_starts(self) -> None:
        result = _run(_balanced_squad())

        assert 1 in result.starting_xi
        assert result.bench_goalkeeper == 2

    def test_lower_projected_goalkeeper_is_always_the_bench_goalkeeper(self) -> None:
        squad = _balanced_squad()
        # Flip which goalkeeper projects higher.
        squad[0] = _candidate(1, GK, 1.0)
        squad[1] = _candidate(2, GK, 5.0)

        result = _run(squad)

        assert 2 in result.starting_xi
        assert result.bench_goalkeeper == 1


class TestBenchOrdering:
    def test_outfield_bench_is_ordered_by_descending_projected_points(self) -> None:
        result = _run(_balanced_squad())

        # Non-starting outfield players here: defender 6 (1.0), defender 7
        # (0.5), midfielder 11 (0.2) or 12 (0.1) depending on formation.
        assert len(result.bench_outfield) == 3
        bench_points = {6: 1.0, 7: 0.5, 11: 0.2, 12: 0.1}
        ordered_points = [bench_points[player_id] for player_id in result.bench_outfield]
        assert ordered_points == sorted(ordered_points, reverse=True)

    def test_bench_goalkeeper_is_never_in_the_outfield_bench(self) -> None:
        result = _run(_balanced_squad())
        assert result.bench_goalkeeper not in result.bench_outfield


class TestCaptaincy:
    def test_captain_is_the_highest_projected_starter(self) -> None:
        result = _run(_balanced_squad())
        assert result.captain == 13  # highest projected points overall (4.5)

    def test_vice_captain_is_the_second_highest_projected_starter(self) -> None:
        result = _run(_balanced_squad())
        assert result.vice_captain == 14  # second highest (4.0)

    def test_captain_and_vice_captain_are_different_players(self) -> None:
        result = _run(_balanced_squad())
        assert result.captain != result.vice_captain


class TestScoring:
    def test_starting_xi_points_is_the_sum_of_starters_projected_points(self) -> None:
        squad = _balanced_squad()
        result = _run(squad)

        points_by_id = {c.player_id: c.projected_points for c in squad}
        expected = sum(points_by_id[player_id] for player_id in result.starting_xi)
        assert result.starting_xi_points == pytest.approx(expected)

    def test_captain_adjusted_points_adds_the_captains_own_points_again(self) -> None:
        # CAPTAIN_MULTIPLIER is 2, so the doubling adds exactly one more
        # helping of the captain's own points on top of starting_xi_points.
        result = _run(_balanced_squad())

        captain_points = 4.5  # forward 13
        assert result.captain_adjusted_points == pytest.approx(
            result.starting_xi_points + captain_points
        )


class TestDeterministicTieBreaking:
    def test_tied_captain_candidates_resolve_to_the_lower_player_id(self) -> None:
        squad = _balanced_squad()
        squad[12] = _candidate(13, FWD, 4.0)  # now tied with forward 14 at 4.0

        result = _run(squad)

        assert result.captain == 13

    def test_tied_bench_candidates_resolve_to_the_lower_player_id_first(self) -> None:
        squad = _balanced_squad()
        # Both are already comfortably below the top-3 midfield cutoff, so
        # the tie sits entirely within the bench group, not the boundary.
        squad[11] = _candidate(12, MID, 0.2)

        result = _run(squad)

        tied_bench = [player_id for player_id in result.bench_outfield if player_id in (11, 12)]
        assert tied_bench == [11, 12]

    def test_identical_input_produces_an_identical_result(self) -> None:
        squad = _balanced_squad()

        first = _run(squad)
        second = _run(squad)

        assert first == second


class TestInputValidation:
    def test_rejects_a_squad_that_is_not_fifteen_players(self) -> None:
        with pytest.raises(RuleViolationError) as error:
            optimise_lineup(_balanced_squad()[:14])
        assert error.value.code == "squad_size"

    def test_rejects_duplicate_player_ids(self) -> None:
        squad = _balanced_squad()
        squad[1] = _candidate(1, GK, 2.0)  # duplicates player 1's id

        with pytest.raises(RuleViolationError) as error:
            optimise_lineup(squad)
        assert error.value.code == "duplicate_player"

    def test_rejects_the_wrong_position_counts(self) -> None:
        squad = _balanced_squad()
        squad[14] = _candidate(15, MID, 3.8)  # now 4 FWD... wait 2 MID extra

        with pytest.raises(RuleViolationError) as error:
            optimise_lineup(squad)
        assert error.value.code == "squad_positions"
