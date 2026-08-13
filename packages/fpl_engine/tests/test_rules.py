from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import (
    Chip,
    RuleViolationError,
    SeasonHalf,
    SquadSlot,
    available_chips,
    diff_squads,
    free_transfers_after,
    has_unlimited_transfers,
    points_hit,
    score_gameweek,
    season_half,
    validate_chip_usage,
    validate_squad,
    validate_squad_composition,
    validate_starting_formation,
)

SQUAD_TEMPLATE: tuple[tuple[PlayerPosition, bool], ...] = (
    (PlayerPosition.GOALKEEPER, True),
    (PlayerPosition.DEFENDER, True),
    (PlayerPosition.DEFENDER, True),
    (PlayerPosition.DEFENDER, True),
    (PlayerPosition.DEFENDER, True),
    (PlayerPosition.MIDFIELDER, True),
    (PlayerPosition.MIDFIELDER, True),
    (PlayerPosition.MIDFIELDER, True),
    (PlayerPosition.MIDFIELDER, True),
    (PlayerPosition.FORWARD, True),
    (PlayerPosition.FORWARD, True),
    (PlayerPosition.GOALKEEPER, False),
    (PlayerPosition.DEFENDER, False),
    (PlayerPosition.MIDFIELDER, False),
    (PlayerPosition.FORWARD, False),
)


def build_squad(
    *, captain_id: int = 1, vice_captain_id: int = 2, first_player_id: int = 1
) -> list[SquadSlot]:
    slots: list[SquadSlot] = []
    bench_order = 0
    for index, (position, is_starting) in enumerate(SQUAD_TEMPLATE):
        player_id = first_player_id + index
        if not is_starting:
            bench_order += 1
        slots.append(
            SquadSlot(
                player_id=player_id,
                position=position,
                team_id=index % 5,
                is_starting=is_starting,
                bench_order=None if is_starting else bench_order,
                is_captain=player_id == captain_id,
                is_vice_captain=player_id == vice_captain_id,
            )
        )
    return slots


class TestSquadValidation:
    def test_valid_squad_passes(self) -> None:
        validate_squad(build_squad())

    def test_rejects_wrong_squad_size(self) -> None:
        with pytest.raises(RuleViolationError) as error:
            validate_squad_composition(build_squad()[:14])
        assert error.value.code == "squad_size"

    def test_rejects_duplicate_players(self) -> None:
        squad = build_squad()
        squad[1] = replace(squad[1], player_id=squad[0].player_id)
        with pytest.raises(RuleViolationError) as error:
            validate_squad_composition(squad)
        assert error.value.code == "duplicate_player"

    def test_rejects_more_than_three_players_from_one_team(self) -> None:
        squad = [replace(slot, team_id=1) for slot in build_squad()]
        with pytest.raises(RuleViolationError) as error:
            validate_squad_composition(squad)
        assert error.value.code == "club_limit"

    def test_rejects_captain_as_vice_captain(self) -> None:
        with pytest.raises(RuleViolationError) as error:
            validate_squad_composition(build_squad(captain_id=1, vice_captain_id=1))
        assert error.value.code == "captain"

    def test_rejects_illegal_formation(self) -> None:
        squad = build_squad()
        # Bench a defender and start the reserve goalkeeper: two keepers in the XI.
        squad[1] = replace(squad[1], is_starting=False, bench_order=1)
        squad[11] = replace(squad[11], is_starting=True, bench_order=None)
        with pytest.raises(RuleViolationError) as error:
            validate_starting_formation(squad)
        assert error.value.code == "formation"

    def test_allows_five_two_three_formation(self) -> None:
        positions = (
            [PlayerPosition.GOALKEEPER]
            + [PlayerPosition.DEFENDER] * 5
            + [PlayerPosition.MIDFIELDER] * 2
            + [PlayerPosition.FORWARD] * 3
        )
        slots = [
            SquadSlot(
                player_id=index,
                position=position,
                team_id=index,
                is_starting=True,
                bench_order=None,
                is_captain=False,
                is_vice_captain=False,
            )
            for index, position in enumerate(positions)
        ]
        validate_starting_formation(slots)


class TestChips:
    @pytest.mark.parametrize(
        ("gameweek", "expected"),
        [
            (1, SeasonHalf.FIRST),
            (19, SeasonHalf.FIRST),
            (20, SeasonHalf.SECOND),
            (38, SeasonHalf.SECOND),
        ],
    )
    def test_season_half_boundary(self, gameweek: int, expected: SeasonHalf) -> None:
        assert season_half(gameweek) is expected

    @pytest.mark.parametrize("gameweek", [0, 39])
    def test_rejects_gameweek_outside_season(self, gameweek: int) -> None:
        with pytest.raises(RuleViolationError) as error:
            season_half(gameweek)
        assert error.value.code == "gameweek_out_of_range"

    def test_same_chip_allowed_once_per_half(self) -> None:
        validate_chip_usage({4: Chip.WILDCARD, 22: Chip.WILDCARD})

    def test_same_chip_twice_in_one_half_rejected(self) -> None:
        with pytest.raises(RuleViolationError) as error:
            validate_chip_usage({4: Chip.WILDCARD, 10: Chip.WILDCARD})
        assert error.value.code == "chip_already_used"

    def test_different_chips_in_same_half_allowed(self) -> None:
        validate_chip_usage({4: Chip.WILDCARD, 10: Chip.BENCH_BOOST, 12: Chip.TRIPLE_CAPTAIN})

    def test_available_chips_excludes_chips_used_in_same_half(self) -> None:
        assert available_chips(10, {4: Chip.WILDCARD, 25: Chip.BENCH_BOOST}) == frozenset(
            {Chip.FREE_HIT, Chip.BENCH_BOOST, Chip.TRIPLE_CAPTAIN}
        )

    def test_available_chips_ignores_chip_set_on_the_target_gameweek(self) -> None:
        assert Chip.WILDCARD in available_chips(4, {4: Chip.WILDCARD})


class TestTransfers:
    def test_diff_reports_players_in_and_out(self) -> None:
        diff = diff_squads([1, 2, 3], [1, 2, 4])
        assert diff.players_out == (3,)
        assert diff.players_in == (4,)
        assert diff.transfer_count == 1

    def test_diff_ignores_reordering(self) -> None:
        assert diff_squads([1, 2, 3], [3, 2, 1]).transfer_count == 0

    def test_no_hit_within_free_transfers(self) -> None:
        assert (
            points_hit(transfers_made=2, free_transfers_available=2, chip=None, gameweek_number=5)
            == 0
        )

    def test_hit_of_four_points_per_extra_transfer(self) -> None:
        assert (
            points_hit(transfers_made=4, free_transfers_available=1, chip=None, gameweek_number=5)
            == 12
        )

    @pytest.mark.parametrize("chip", [Chip.WILDCARD, Chip.FREE_HIT])
    def test_no_hit_on_unlimited_transfer_chips(self, chip: Chip) -> None:
        assert (
            points_hit(transfers_made=9, free_transfers_available=0, chip=chip, gameweek_number=5)
            == 0
        )

    def test_gameweek_one_is_free(self) -> None:
        assert has_unlimited_transfers(gameweek_number=1, chip=None) is True
        assert (
            points_hit(transfers_made=15, free_transfers_available=0, chip=None, gameweek_number=1)
            == 0
        )

    def test_gameweek_two_starts_with_exactly_one_free_transfer(self) -> None:
        assert (
            free_transfers_after(available=0, transfers_made=15, chip=None, gameweek_number=1) == 1
        )

    def test_unused_transfers_accumulate(self) -> None:
        assert (
            free_transfers_after(available=1, transfers_made=0, chip=None, gameweek_number=2) == 2
        )

    def test_accumulation_caps_at_five(self) -> None:
        assert (
            free_transfers_after(available=5, transfers_made=0, chip=None, gameweek_number=9) == 5
        )

    def test_used_transfers_reduce_the_bank(self) -> None:
        assert (
            free_transfers_after(available=3, transfers_made=3, chip=None, gameweek_number=9) == 1
        )

    def test_hits_never_push_the_bank_negative(self) -> None:
        assert (
            free_transfers_after(available=1, transfers_made=4, chip=None, gameweek_number=9) == 1
        )

    @pytest.mark.parametrize("chip", [Chip.WILDCARD, Chip.FREE_HIT])
    def test_unlimited_chips_preserve_banked_transfers(self, chip: Chip) -> None:
        assert (
            free_transfers_after(available=3, transfers_made=8, chip=chip, gameweek_number=9) == 4
        )


class TestScoring:
    projected: ClassVar[dict[int, float]] = {index: float(index) for index in range(1, 16)}

    def test_starters_and_captain_double(self) -> None:
        score = score_gameweek(slots=build_squad(captain_id=11), projected_points=self.projected)
        assert score.starting_points == sum(range(1, 12))
        assert score.captain_bonus_points == 11.0
        assert score.bench_boost_applied is False
        assert score.total_points == sum(range(1, 12)) + 11.0

    def test_bench_excluded_without_bench_boost(self) -> None:
        score = score_gameweek(slots=build_squad(captain_id=11), projected_points=self.projected)
        assert score.bench_points == sum(range(12, 16))
        assert score.total_points == score.starting_points + score.captain_bonus_points

    def test_bench_boost_counts_all_fifteen(self) -> None:
        score = score_gameweek(
            slots=build_squad(captain_id=11),
            projected_points=self.projected,
            chip=Chip.BENCH_BOOST,
        )
        assert score.total_points == sum(range(1, 16)) + 11.0

    def test_triple_captain_triples_the_captain(self) -> None:
        score = score_gameweek(
            slots=build_squad(captain_id=11),
            projected_points=self.projected,
            chip=Chip.TRIPLE_CAPTAIN,
        )
        assert score.captain_bonus_points == 22.0

    def test_benched_captain_scores_nothing_extra(self) -> None:
        score = score_gameweek(slots=build_squad(captain_id=15), projected_points=self.projected)
        assert score.captain_bonus_points == 0.0

    def test_points_hit_is_deducted(self) -> None:
        score = score_gameweek(
            slots=build_squad(captain_id=11),
            projected_points=self.projected,
            points_hit=8,
        )
        assert score.total_points == sum(range(1, 12)) + 11.0 - 8
