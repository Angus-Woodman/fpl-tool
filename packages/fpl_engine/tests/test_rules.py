from __future__ import annotations

from dataclasses import replace
from typing import ClassVar

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import (
    STARTING_POSITION_LIMITS,
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


class TestPlannerChipPeriods:
    def test_exactly_four_chips_and_unused_first_period_lapses(self) -> None:
        from fpl_engine.rules.chips import chip_states

        assert {chip.value for chip in Chip} == {
            "WILDCARD",
            "FREE_HIT",
            "BENCH_BOOST",
            "TRIPLE_CAPTAIN",
        }
        for chip in Chip:
            assert chip_states(20, {}, start_gameweek=17)[chip].state == "available"
            assert chip_states(38, {20: chip}, start_gameweek=17)[chip].state == "planned_elsewhere"

    @pytest.mark.parametrize("chip", list(Chip))
    @pytest.mark.parametrize(("first", "second"), [(17, 19), (20, 38)])
    def test_once_per_period_names_the_existing_gameweek(self, chip, first, second) -> None:
        from fpl_engine.planning.models import SetChip
        from fpl_engine.planning.mutations import apply_intents
        from test_planning import build_plan, metadata

        plan = apply_intents(build_plan(17, 38), (SetChip(first, chip, None),), metadata()).plan
        with pytest.raises(RuleViolationError, match=f"Planned for gameweek {first}"):
            apply_intents(plan, (SetChip(second, chip, None),), metadata())
        assert next(week for week in plan.gameweeks if week.gameweek_number == second).chip is None

    @pytest.mark.parametrize("chip", list(Chip))
    def test_used_before_is_not_planned_elsewhere_and_resets_at_20(self, chip) -> None:
        from fpl_engine.planning.models import SetChip
        from fpl_engine.planning.mutations import apply_intents
        from fpl_engine.rules.chips import chip_states
        from test_planning import build_plan, metadata

        plan = build_plan(17, 22)
        plan = replace(plan, boundary=replace(plan.boundary, used_chips=frozenset({chip})))
        state = chip_states(18, {}, start_gameweek=17, used_chips=plan.boundary.used_chips)[chip]
        assert (state.state, state.reason, state.conflicting_gameweek) == (
            "used_before",
            "Used before this plan",
            None,
        )
        with pytest.raises(RuleViolationError, match="Used before this plan"):
            apply_intents(plan, (SetChip(18, chip, None),), metadata())
        changed = apply_intents(plan, (SetChip(20, chip, None),), metadata()).plan
        assert changed.gameweeks[3].chip == chip

    @pytest.mark.parametrize("chip", list(Chip))
    def test_gameweek_one_restrictions(self, chip) -> None:
        from fpl_engine.planning.models import SetChip
        from fpl_engine.planning.mutations import apply_intents
        from test_planning import build_plan, metadata

        plan = build_plan(1, 2)
        if chip in {Chip.WILDCARD, Chip.FREE_HIT}:
            with pytest.raises(RuleViolationError, match="unavailable in gameweek 1"):
                apply_intents(plan, (SetChip(1, chip, None),), metadata())
        else:
            assert (
                apply_intents(plan, (SetChip(1, chip, None),), metadata()).plan.gameweeks[0].chip
                == chip
            )

    @pytest.mark.parametrize(("first", "second"), [(19, 20), (20, 19)])
    @pytest.mark.parametrize("chip", list(Chip))
    def test_cross_boundary_use_in_either_order(self, chip, first, second) -> None:
        from fpl_engine.planning.models import SetChip
        from fpl_engine.planning.mutations import apply_intents
        from test_planning import build_plan, metadata

        plan = apply_intents(build_plan(19, 20), (SetChip(first, chip, None),), metadata()).plan
        if chip == Chip.FREE_HIT:
            with pytest.raises(
                RuleViolationError, match=f"Free Hit conflicts with gameweek {first}"
            ):
                apply_intents(plan, (SetChip(second, chip, None),), metadata())
        else:
            assert all(
                week.chip == chip
                for week in apply_intents(
                    plan, (SetChip(second, chip, None),), metadata()
                ).plan.gameweeks
            )

    @pytest.mark.parametrize("declaration_first", [False, True])
    def test_free_hit_19_declaration_conflicts_in_either_direction(self, declaration_first) -> None:
        from fpl_engine.planning.models import SetChip, SetStartingChips
        from fpl_engine.planning.mutations import apply_intents
        from test_planning import build_plan, metadata

        declaration = SetStartingChips(frozenset(), True)
        activation = SetChip(20, Chip.FREE_HIT, None)
        first, second = (
            (declaration, activation) if declaration_first else (activation, declaration)
        )
        plan = apply_intents(build_plan(20, 21), (first,), metadata()).plan
        with pytest.raises(RuleViolationError, match="Free Hit conflicts with gameweek 19"):
            apply_intents(plan, (second,), metadata())

    def test_atomic_chip_moves_removals_and_occupied_targets_preserve_quotes(self) -> None:
        from fpl_engine.planning.models import MoveChip, SetChip
        from fpl_engine.planning.mutations import apply_intents
        from fpl_engine.rules.chips import chip_states
        from test_planning import build_plan, build_transfer, metadata, with_week

        decision = build_transfer()
        plan = with_week(build_plan(17, 22), 18, chip=Chip.WILDCARD, transfers=(decision,))
        plan = with_week(plan, 19, chip=Chip.BENCH_BOOST)
        with pytest.raises(RuleViolationError, match="source/target has changed"):
            apply_intents(plan, (MoveChip(18, 19, Chip.WILDCARD),), metadata())
        with pytest.raises(RuleViolationError, match="Remove the existing chip"):
            apply_intents(plan, (SetChip(18, Chip.TRIPLE_CAPTAIN, Chip.WILDCARD),), metadata())
        moved = apply_intents(
            plan, (SetChip(19, None, Chip.BENCH_BOOST), MoveChip(18, 19, Chip.WILDCARD)), metadata()
        ).plan
        assert [week.chip for week in moved.gameweeks] == [
            None,
            None,
            Chip.WILDCARD,
            None,
            None,
            None,
        ]
        assert moved.gameweeks[1].transfers == (decision,)
        cleared = apply_intents(moved, (SetChip(19, None, Chip.WILDCARD),), metadata()).plan
        chips = {week.gameweek_number: week.chip for week in cleared.gameweeks}
        assert chip_states(17, chips, start_gameweek=17)[Chip.WILDCARD].state == "available"
        assert cleared.gameweeks[1].transfers == (decision,)
        assert all(not week.transfers for week in cleared.gameweeks if week.gameweek_number != 18)


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

    def test_validate_squad_accepts_a_full_five_two_three_squad(self) -> None:
        # MID=2 is legal; a frontend rule requiring MID >= 3 would wrongly block this.
        template = (
            [(PlayerPosition.GOALKEEPER, True)]
            + [(PlayerPosition.DEFENDER, True)] * 5
            + [(PlayerPosition.MIDFIELDER, True)] * 2
            + [(PlayerPosition.FORWARD, True)] * 3
            + [(PlayerPosition.GOALKEEPER, False)]
            + [(PlayerPosition.MIDFIELDER, False)] * 3
        )
        slots: list[SquadSlot] = []
        bench_order = 0
        for index, (position, is_starting) in enumerate(template):
            if not is_starting:
                bench_order += 1
            slots.append(
                SquadSlot(
                    player_id=index + 1,
                    position=position,
                    team_id=index % 5,
                    is_starting=is_starting,
                    bench_order=None if is_starting else bench_order,
                    is_captain=index == 0,
                    is_vice_captain=index == 1,
                )
            )
        validate_squad(slots)

    def test_validate_squad_rejects_two_starting_goalkeepers(self) -> None:
        squad = build_squad()
        # Bench a defender (order 1) and start the reserve goalkeeper; bench orders stay unique.
        squad[1] = replace(squad[1], is_starting=False, bench_order=1)
        squad[11] = replace(squad[11], is_starting=True, bench_order=None)
        with pytest.raises(RuleViolationError) as error:
            validate_squad(squad)
        assert error.value.code == "formation"


class TestRearrangement:
    """Shared starter/bench rearrangement used by My Team and the Planner (FR-043 to FR-045)."""

    @staticmethod
    def pairs(slots: list[SquadSlot]) -> set[tuple[frozenset[int], str]]:
        from fpl_engine.rules import legal_rearrangements

        return {
            (frozenset({choice.first_player_id, choice.second_player_id}), choice.kind)
            for choice in legal_rearrangements(slots)
        }

    @staticmethod
    def by_id(slots: object) -> dict[int, SquadSlot]:
        return {slot.player_id: slot for slot in slots}  # type: ignore[attr-defined]

    def test_offers_each_legal_pair_once_with_its_kind(self) -> None:
        from fpl_engine.rules import legal_rearrangements

        slots = build_squad(captain_id=2, vice_captain_id=3)
        choices = legal_rearrangements(slots)
        assert len(choices) == len(
            {frozenset({c.first_player_id, c.second_player_id}) for c in choices}
        )
        found = self.pairs(slots)
        # 4-4-2 XI, bench GK/DEF/MID/FWD: GK swaps with GK only; outfield starters swap with
        # outfield subs when the formation survives; only the three outfield subs reorder.
        assert (frozenset({1, 12}), "substitution") in found
        assert (frozenset({2, 13}), "substitution") in found
        assert (frozenset({2, 14}), "substitution") in found
        assert (frozenset({13, 14}), "bench_priority") in found
        assert (frozenset({13, 15}), "bench_priority") in found
        assert (frozenset({14, 15}), "bench_priority") in found

    def test_goalkeeper_is_never_a_target_for_outfield_players_or_bench_priority(self) -> None:
        found = self.pairs(build_squad(captain_id=2, vice_captain_id=3))
        keepers = {1, 12}
        for players, kind in found:
            if players & keepers:
                assert players == keepers
                assert kind == "substitution"
        assert not any(kind == "bench_priority" and players & keepers for players, kind in found)

    def test_formation_limits_filter_targets(self) -> None:
        # Three defenders in the XI: only a defender may replace one of them.
        squad = build_squad(captain_id=2, vice_captain_id=3)
        squad[4] = replace(squad[4], is_starting=False, bench_order=3)
        squad[13] = replace(squad[13], is_starting=True, bench_order=None)
        validate_squad(squad)
        found = self.pairs(squad)
        assert (frozenset({2, 13}), "substitution") in found
        assert (frozenset({2, 5}), "substitution") in found
        assert (frozenset({2, 15}), "substitution") not in found
        assert (frozenset({10, 15}), "substitution") in found

    def test_starter_with_bench_swap_moves_roles_and_captaincy_follows_the_slot(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        slots = build_squad(captain_id=2, vice_captain_id=3)
        result = self.by_id(rearrange_lineup(slots, 2, 14))
        assert (result[14].is_starting, result[14].bench_order) == (True, None)
        assert (result[14].is_captain, result[14].is_vice_captain) == (True, False)
        assert (result[2].is_starting, result[2].bench_order) == (False, 3)
        assert (result[2].is_captain, result[2].is_vice_captain) == (False, False)
        untouched = {
            player_id: slot
            for player_id, slot in self.by_id(slots).items()
            if player_id not in {2, 14}
        }
        assert all(result[player_id] == slot for player_id, slot in untouched.items())

    def test_vice_captain_is_inherited_in_the_same_way(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        slots = build_squad(captain_id=2, vice_captain_id=3)
        result = self.by_id(rearrange_lineup(slots, 15, 3))
        assert (result[15].is_starting, result[15].is_vice_captain, result[15].is_captain) == (
            True,
            True,
            False,
        )
        assert (result[3].is_starting, result[3].bench_order, result[3].is_vice_captain) == (
            False,
            4,
            False,
        )

    def test_argument_order_does_not_change_the_result(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        slots = build_squad(captain_id=2, vice_captain_id=3)
        assert rearrange_lineup(slots, 2, 14) == rearrange_lineup(slots, 14, 2)
        assert rearrange_lineup(slots, 13, 15) == rearrange_lineup(slots, 15, 13)

    def test_outfield_bench_priority_swaps_only_the_bench_order(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        slots = build_squad(captain_id=2, vice_captain_id=3)
        result = self.by_id(rearrange_lineup(slots, 13, 15))
        assert (result[13].bench_order, result[15].bench_order) == (4, 2)
        assert (result[14].bench_order, result[12].bench_order) == (3, 1)
        assert all(
            result[player_id] == slot
            for player_id, slot in self.by_id(slots).items()
            if player_id not in {13, 15}
        )

    @pytest.mark.parametrize("pair", [(12, 13), (14, 12), (12, 15)])
    def test_bench_goalkeeper_cannot_reorder_with_outfield_substitutes(self, pair) -> None:
        from fpl_engine.rules import rearrange_lineup

        with pytest.raises(RuleViolationError) as error:
            rearrange_lineup(build_squad(), *pair)
        assert error.value.code == "invalid_swap"
        assert "Goalkeeper" in str(error.value)

    def test_two_starters_the_same_player_and_unknown_players_are_rejected(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        slots = build_squad()
        for pair in [(2, 3), (2, 2), (2, 99), (99, 98)]:
            with pytest.raises(RuleViolationError) as error:
                rearrange_lineup(slots, *pair)
            assert error.value.code == "invalid_swap"

    def test_illegal_formation_swap_is_rejected_by_the_squad_rules(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        with pytest.raises(RuleViolationError) as error:
            rearrange_lineup(build_squad(captain_id=2, vice_captain_id=3), 5, 12)
        assert error.value.code == "formation"

    def test_enumeration_and_execution_always_agree(self) -> None:
        from fpl_engine.rules import rearrange_lineup

        slots = build_squad(captain_id=2, vice_captain_id=3)
        offered = {pair for pair, _ in self.pairs(slots)}
        for first in slots:
            for second in slots:
                if first.player_id >= second.player_id:
                    continue
                pair = frozenset({first.player_id, second.player_id})
                try:
                    result = rearrange_lineup(slots, first.player_id, second.player_id)
                except RuleViolationError:
                    assert pair not in offered
                else:
                    assert pair in offered
                    validate_squad(result)

    def test_inputs_are_not_mutated_and_invalid_squads_offer_nothing(self) -> None:
        from fpl_engine.rules import legal_rearrangements

        slots = build_squad(captain_id=2, vice_captain_id=3)
        before = list(slots)
        legal_rearrangements(slots)
        assert slots == before
        assert legal_rearrangements([replace(slot, team_id=1) for slot in slots]) == ()

    def test_formation_limits_are_the_single_authority(self, monkeypatch) -> None:
        # Tightening the shared limit must change the offered targets; no copy exists elsewhere.
        slots = build_squad(captain_id=2, vice_captain_id=3)
        assert (frozenset({2, 14}), "substitution") in self.pairs(slots)
        monkeypatch.setitem(STARTING_POSITION_LIMITS, PlayerPosition.DEFENDER, (4, 4))
        assert (frozenset({2, 14}), "substitution") not in self.pairs(slots)


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
    @pytest.mark.parametrize(
        ("available", "expected"), [(0, 1), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]
    )
    def test_unlimited_chips_consume_the_arising_transfer(
        self, chip: Chip, available: int, expected: int
    ) -> None:
        assert (
            free_transfers_after(
                available=available, transfers_made=8, chip=chip, gameweek_number=9
            )
            == expected
        )

    @pytest.mark.parametrize("chip", [Chip.BENCH_BOOST, Chip.TRIPLE_CAPTAIN])
    @pytest.mark.parametrize(("moves", "next_ft", "hit"), [(0, 4, 0), (1, 3, 0), (4, 1, 4)])
    def test_scoring_chips_keep_ordinary_transfer_accounting(
        self, chip: Chip, moves: int, next_ft: int, hit: int
    ) -> None:
        assert (
            free_transfers_after(available=3, transfers_made=moves, chip=chip, gameweek_number=9)
            == next_ft
        )
        assert (
            points_hit(
                transfers_made=moves, free_transfers_available=3, chip=chip, gameweek_number=9
            )
            == hit
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
