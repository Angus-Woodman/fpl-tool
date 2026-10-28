from __future__ import annotations

from dataclasses import replace

import pytest
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.hypothetical import (
    CandidateQuote,
    assess_candidate,
    resolve_transfer_operation,
)
from fpl_engine.planning.impact import (
    GameweekImpact,
    PlanImpact,
    compute_plan_impact,
    horizon_window,
)
from fpl_engine.planning.models import LineupRole, Plan
from fpl_engine.rules import Chip
from planning_reference_plans import (
    OUTGOING_MARKET_TENTHS,
    identity,
    metadata,
    plan,
    reference_plans,
    transfer,
)

META = metadata()


def points(
    gameweeks: range, special: dict[int, float] | None = None
) -> dict[int, dict[int, float]]:
    special = special or {6: 2.0, 106: 5.0}
    return {
        gameweek: {player_id: special.get(player_id, 1.0) for player_id in META}
        for gameweek in gameweeks
    }


def lineup_with(
    reference: Plan,
    gameweek: int,
    *,
    bench: tuple[int, int] | None = None,
    captain: int | None = None,
    final_free_hit_shape: bool = False,
) -> Plan:
    """Change one gameweek's saved roles by player id (slots are identity(player_id))."""
    roles = {role.slot_id: role for role in reference.boundary.lineup}
    if bench is not None:
        benched, starter = bench
        starter_role, bench_role = roles[identity(starter)], roles[identity(benched)]
        roles[identity(benched)] = replace(
            bench_role, is_starting=False, bench_order=starter_role.bench_order
        )
        roles[identity(starter)] = replace(starter_role, is_starting=True, bench_order=None)
    if captain is not None:
        roles = {
            slot: replace(role, is_captain=slot == identity(captain))
            for slot, role in roles.items()
        }
    if final_free_hit_shape:
        # Free Hit XI of 3-4-3 on slots 14 and 13 swapped to DEF/MID; illegal once restored.
        xi = {1, 2, 3, 14, 6, 7, 8, 9, 10, 11, 15}
        bench_order = iter((1, 2, 3, 4))
        roles = {
            slot: LineupRole(
                slot,
                int(slot.int) in xi,
                None if int(slot.int) in xi else next(bench_order),
                int(slot.int) == 2,
                int(slot.int) == 3,
            )
            for slot in roles
        }
    lineup = tuple(roles[role.slot_id] for role in reference.boundary.lineup)
    return replace(
        reference,
        gameweeks=tuple(
            replace(week, lineup=lineup) if week.gameweek_number == gameweek else week
            for week in reference.gameweeks
        ),
    )


def impact_for(
    reference: Plan,
    gameweek: int,
    projections: dict[int, dict[int, float]],
    selected: int = 6,
    candidate: int = 106,
) -> PlanImpact:
    baseline = evaluate_plan(reference, META)
    operation = resolve_transfer_operation(reference, baseline, gameweek, selected)
    result = assess_candidate(
        reference,
        baseline,
        META,
        operation,
        CandidateQuote(candidate, OUTGOING_MARKET_TENTHS, 50),
    )
    assert result.evaluation is not None
    return compute_plan_impact(
        plan=reference,
        baseline=baseline,
        candidate=result.evaluation,
        metadata=META,
        projections=projections,
        gameweek=gameweek,
        valid_through=result.valid_through_gameweek,
    )


def by_gameweek(impact: PlanImpact) -> dict[int, GameweekImpact]:
    return {item.gameweek: item for item in impact.by_gameweek}


def test_impact_uses_the_saved_slot_role_of_each_gameweek() -> None:
    reference = plan()
    reference = lineup_with(reference, 9, bench=(6, 14))  # benched in GW9
    reference = lineup_with(reference, 10, captain=6)  # captain in GW10
    impact = impact_for(reference, 8, points(range(8, 13)))
    weeks = by_gameweek(impact)
    assert [weeks[number].basis for number in (8, 9, 10, 11, 12)] == [
        "saved_plan",
        "saved_plan",
        "saved_plan",
        "saved_plan",
        "assumed_continuation",
    ]
    assert [weeks[number].delta for number in (8, 9, 10, 11, 12)] == [3.0, 0.0, 6.0, 3.0, 3.0]
    assert impact.totals[1].saved_plan == 3.0
    assert impact.totals[3].saved_plan == 9.0
    assert impact.totals[5].saved_plan == 12.0
    assert impact.totals[5].assumed_continuation == 3.0
    assert impact.totals[1].assumed_continuation is None


def test_bench_boost_counts_a_benched_incoming_player_and_triple_captain_triples() -> None:
    boosted = lineup_with(plan(chips={9: Chip.BENCH_BOOST}), 9, bench=(6, 14))
    assert by_gameweek(impact_for(boosted, 8, points(range(8, 11))))[9].delta == 3.0
    triple = lineup_with(plan(chips={9: Chip.TRIPLE_CAPTAIN}), 9, captain=6)
    assert by_gameweek(impact_for(triple, 8, points(range(8, 11))))[9].delta == 9.0


def test_wildcard_acquisition_carries_into_later_gameweeks_without_a_hit() -> None:
    reference = plan(chips={9: Chip.WILDCARD})
    impact = impact_for(reference, 9, points(range(9, 14)))
    assert [item.delta for item in impact.by_gameweek[:3]] == [3.0, 3.0, 3.0]
    assert impact.totals[3].saved_plan == 9.0  # GW9 to GW11, all inside the plan
    assert impact.totals[3].hit_change == 0


def test_a_free_hit_selected_gameweek_limits_the_horizon_to_that_gameweek() -> None:
    reference = plan(chips={9: Chip.FREE_HIT})
    impact = impact_for(reference, 9, points(range(9, 14)))
    assert [item.gameweek for item in impact.by_gameweek] == [9]
    assert impact.totals[5].saved_plan == 3.0
    assert impact.totals[5].assumed_continuation is None
    assert impact.totals[5].limited_reason == "free_hit_gameweek"
    assert impact.totals[5].evaluated_gameweeks == (9,)
    assert impact.totals[5].partial is False


def test_hit_is_excluded_from_impact_and_reported_with_knock_on_effects() -> None:
    reference = plan(
        transfers={9: (transfer(2, 102, 1), transfer(3, 103, 2))},
    )
    impact = impact_for(reference, 8, points(range(8, 13)))
    weeks = by_gameweek(impact)
    assert weeks[8].hit_before == weeks[8].hit_after == 0
    # GW8 used the free transfer banked for GW9: two transfers then cost a hit.
    assert (weeks[9].hit_before, weeks[9].hit_after) == (0, 4)
    assert impact.totals[3].hit_change == 4
    assert impact.totals[3].saved_plan == 9.0  # 3 points a gameweek, hit not deducted
    assert impact.totals[3].net_saved_plan == 5.0
    assert impact.totals[1].hit_change == 0


def test_horizon_past_the_plan_end_is_an_assumed_continuation_with_final_roles() -> None:
    reference = lineup_with(plan(8, 9), 9, captain=6)
    impact = impact_for(reference, 8, points(range(8, 13)))
    weeks = by_gameweek(impact)
    assert [weeks[number].basis for number in (8, 9, 10, 11, 12)] == [
        "saved_plan",
        "saved_plan",
        "assumed_continuation",
        "assumed_continuation",
        "assumed_continuation",
    ]
    assert impact.totals[5].saved_plan == 9.0  # 3.0 in GW8, 6.0 as captain in GW9
    assert impact.totals[5].assumed_continuation == 18.0  # 6.0 in each of GW10 to GW12
    assert all(item.hit_before == item.hit_after == 0 for item in impact.by_gameweek[2:])
    assert not hasattr(impact.totals[5], "combined")


def test_continuation_after_a_final_free_hit_uses_the_restored_squad() -> None:
    reference = plan(8, 9, chips={9: Chip.FREE_HIT})
    impact = impact_for(reference, 8, points(range(8, 13)))
    weeks = by_gameweek(impact)
    assert weeks[9].basis == "saved_plan"
    assert weeks[10].basis == "assumed_continuation"
    assert weeks[10].available and weeks[10].delta == 3.0  # 106 is back in the permanent squad


def test_illegal_restored_roles_are_reported_not_repaired() -> None:
    reference = plan(
        8,
        9,
        chips={9: Chip.FREE_HIT},
        transfers={9: (transfer(14, 113, 1), transfer(13, 114, 2))},
    )
    reference = lineup_with(reference, 9, final_free_hit_shape=True)
    impact = impact_for(reference, 8, points(range(8, 13)))
    weeks = by_gameweek(impact)
    assert weeks[9].available
    for number in (10, 11, 12):
        assert not weeks[number].available
        assert weeks[number].reason == "continuation_lineup_illegal"
        assert weeks[number].delta is None
    assert impact.totals[5].assumed_continuation is None
    assert impact.totals[5].saved_plan == 6.0


def test_values_beyond_the_validity_limit_are_absent_never_estimated() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "later_sale_of_a_player"
    )
    impact = impact_for(reference, 8, points(range(8, 13)))
    weeks = by_gameweek(impact)
    assert weeks[8].available and weeks[9].available
    for number in (10, 11, 12):
        assert not weeks[number].available
        assert weeks[number].reason == "beyond_valid_range"
        assert weeks[number].points_after is None and weeks[number].delta is None
    assert impact.totals[5].saved_plan == 6.0
    assert impact.totals[5].assumed_continuation is None
    assert impact.totals[5].valid_through_gameweek == 9


def test_projection_coverage_is_the_contiguous_run_from_the_selected_gameweek() -> None:
    reference = plan(8, 12)
    projections = points(range(8, 13))
    del projections[10]  # a gap ends coverage: GW11 and GW12 are not evaluated
    impact = impact_for(reference, 8, projections)
    assert [item.gameweek for item in impact.by_gameweek] == [8, 9]
    assert impact.totals[5].evaluated_gameweeks == (8, 9)
    assert impact.totals[5].requested_gameweeks == (8, 9, 10, 11, 12)
    assert impact.totals[5].partial is True
    assert impact.totals[1].partial is False
    assert impact.totals[5].saved_plan == 6.0


def test_horizon_window_describes_requested_evaluated_and_basis_gameweeks() -> None:
    reference = plan(8, 9)
    window = horizon_window(reference, 8, 5, {8, 9, 10, 11})
    assert window.requested == (8, 9, 10, 11, 12)
    assert window.evaluated == (8, 9, 10, 11)
    assert window.saved_plan == (8, 9) and window.assumed == (10, 11)
    assert window.partial and window.limited_reason is None
    capped = horizon_window(plan(36, 37), 36, 5, set(range(36, 39)))
    assert capped.requested == (36, 37, 38)  # the season ends at gameweek 38
    assert capped.partial is False
    with pytest.raises(ValueError):
        horizon_window(reference, 8, 4, {8})
