from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.hypothetical import (
    CandidateAssessment,
    CandidateQuote,
    assess_candidate,
    resolve_transfer_operation,
)
from fpl_engine.planning.models import AddTransfer, EditTransfer, Plan, PlanEvaluation
from fpl_engine.planning.mutations import MutationRejectedError, apply_intents
from fpl_engine.rules import Chip, RuleViolationError
from planning_reference_plans import (
    CLUB_LIMIT_CANDIDATE,
    OUTGOING_MARKET_TENTHS,
    candidate_price,
    identity,
    metadata,
    plan,
    reference_plans,
    transfer,
)

META = metadata()


def squad_at(evaluation: PlanEvaluation, gameweek: int) -> tuple[int, ...]:
    week = next(item for item in evaluation.gameweeks if item.gameweek_number == gameweek)
    assert week.players is not None
    return tuple(player.player_id for player in week.players)


def pool(evaluation: PlanEvaluation, gameweek: int, selected: int) -> list[int]:
    squad = set(squad_at(evaluation, gameweek))
    return [
        player_id
        for player_id, rule in sorted(META.items())
        if player_id not in squad and rule.position == META[selected].position
    ]


def assess(
    reference: Plan, gameweek: int, selected: int, candidate: int, evaluation: PlanEvaluation
) -> CandidateAssessment:
    operation = resolve_transfer_operation(reference, evaluation, gameweek, selected)
    return assess_candidate(
        reference,
        evaluation,
        META,
        operation,
        CandidateQuote(candidate, OUTGOING_MARKET_TENTHS, candidate_price(candidate)),
    )


def test_verdict_equals_apply_intents_for_every_pool_candidate_of_every_reference_plan() -> None:
    checked = 0
    for reference in reference_plans():
        evaluation = evaluate_plan(reference.plan, META)
        for gameweek in reference.gameweeks:
            for selected in squad_at(evaluation, gameweek):
                for candidate in pool(evaluation, gameweek, selected):
                    result = assess(reference.plan, gameweek, selected, candidate, evaluation)
                    context = (reference.name, gameweek, selected, candidate)
                    if result.decision is None:
                        # Not expressible as a Planner decision (same-gameweek round trip).
                        assert result.reasons == ("sold_this_gameweek",), context
                        assert not result.confirmable and result.plan is None, context
                        if result.operation.kind == "add_transfer":
                            manual = transfer(
                                selected,
                                candidate,
                                900 + checked,
                                incoming_price=candidate_price(candidate),
                                outgoing_ownership=result.operation.sold_ownership_id,
                            )
                            with pytest.raises(RuleViolationError):
                                apply_intents(
                                    reference.plan, (AddTransfer(gameweek, manual),), META
                                )
                        checked += 1
                        continue
                    intent = (
                        EditTransfer(result.decision.decision_id, result.decision)
                        if result.operation.kind == "edit_transfer"
                        else AddTransfer(gameweek, result.decision)
                    )
                    try:
                        applied = apply_intents(reference.plan, (intent,), META)
                    except MutationRejectedError as error:
                        assert not result.confirmable, context
                        first = error.diagnostics[0]
                        assert (first.code, first.gameweek_number) in {
                            (conflict.code, conflict.gameweek) for conflict in result.conflicts
                        }, context
                    else:
                        assert result.confirmable, context
                        assert result.plan == applied.plan, context
                        assert result.evaluation == applied.evaluation, context
                    checked += 1
    assert checked > 500


def test_operation_is_an_edit_only_for_an_acquisition_made_in_the_same_gameweek() -> None:
    reference = plan(transfers={9: (transfer(2, 102, 1),)})
    evaluation = evaluate_plan(reference, META)
    add = resolve_transfer_operation(reference, evaluation, 9, 6)
    assert (add.kind, add.replaces_decision_id) == ("add_transfer", None)
    assert (add.selected_player_id, add.sold_player_id) == (6, 6)
    assert add.sold_ownership_id == identity(1006)
    edit = resolve_transfer_operation(reference, evaluation, 9, 102)
    assert (edit.kind, edit.replaces_decision_id) == ("edit_transfer", identity(2001))
    assert (edit.selected_player_id, edit.sold_player_id) == (102, 2)
    assert edit.sold_ownership_id == identity(1002)
    later = resolve_transfer_operation(reference, evaluation, 10, 102)
    assert later.kind == "add_transfer"
    assert later.sold_ownership_id == identity(3001)


def test_replacing_a_same_gameweek_acquisition_replaces_it_instead_of_stacking() -> None:
    reference = plan(transfers={9: (transfer(2, 102, 1),)})
    evaluation = evaluate_plan(reference, META)
    result = assess(reference, 9, 102, 105, evaluation)
    assert result.state == "available"
    assert result.plan is not None
    week = result.plan.gameweeks[1]
    assert [(item.outgoing_player_id, item.incoming_player_id) for item in week.transfers] == [
        (2, 105)
    ]
    assert week.transfers[0].decision_id == identity(2001)
    assert result.selling_price_tenths is None
    assert result.resulting_bank_tenths == 10 + 52 - candidate_price(105)


def test_resolving_an_operation_reports_the_precise_input_error() -> None:
    reference = plan()
    evaluation = evaluate_plan(reference, META)
    with pytest.raises(RuleViolationError) as missing:
        resolve_transfer_operation(reference, evaluation, 8, 999)
    assert missing.value.code == "player_not_in_squad"
    with pytest.raises(RuleViolationError) as outside:
        resolve_transfer_operation(reference, evaluation, 20, 6)
    assert outside.value.code == "gameweek_not_in_plan"
    broken = plan(transfers={8: (replace(transfer(6, 106, 1), outgoing_ownership_id=identity(9)),)})
    with pytest.raises(RuleViolationError) as blocked:
        resolve_transfer_operation(broken, evaluate_plan(broken, META), 8, 7)
    assert blocked.value.code == "evaluation_blocked"


def test_ordinary_gameweek_matches_the_hand_calculation() -> None:
    reference = plan()
    evaluation = evaluate_plan(reference, META)
    result = assess(reference, 8, 6, 106, evaluation)
    assert result.state == "available" and result.confirmable
    assert result.operation.kind == "add_transfer"
    assert result.selling_price_tenths == 52  # purchase 5.0, market 5.4: half the rise
    assert result.resulting_bank_tenths == 10 + 52 - 50
    assert result.points_hit_after == 0
    assert result.selling_provisional is True  # the purchase price is an estimate
    assert result.valid_through_gameweek is None
    assert result.reasons == () and result.conflict is None


def test_confirmed_purchase_basis_is_not_provisional() -> None:
    reference = next(item.plan for item in reference_plans() if item.name == "confirmed_basis")
    result = assess(reference, 8, 6, 106, evaluate_plan(reference, META))
    assert result.selling_provisional is False


def test_zero_free_transfers_costs_a_hit_and_gameweek_one_is_hit_free() -> None:
    zero = next(item.plan for item in reference_plans() if item.name == "zero_free_transfers")
    assert assess(zero, 8, 6, 106, evaluate_plan(zero, META)).points_hit_after == 4
    first = next(item.plan for item in reference_plans() if item.name == "starting_gameweek_one")
    result = assess(first, 1, 6, 106, evaluate_plan(first, META))
    assert result.state == "available" and result.points_hit_after == 0


def test_wildcard_is_hit_free_and_permanent_while_free_hit_is_temporary() -> None:
    wildcard = plan(chips={9: Chip.WILDCARD}, base=plan().boundary)
    base = evaluate_plan(wildcard, META)
    result = assess(wildcard, 9, 6, 106, base)
    assert result.points_hit_after == 0
    assert result.evaluation is not None
    later = result.evaluation.gameweeks[2]
    assert later.players is not None
    assert 106 in {player.player_id for player in later.players}
    assert 6 not in {player.player_id for player in later.players}

    hit = plan(chips={9: Chip.FREE_HIT})
    hit_base = evaluate_plan(hit, META)
    temporary = assess(hit, 9, 6, 106, hit_base)
    assert temporary.points_hit_after == 0
    assert temporary.evaluation is not None
    restored = temporary.evaluation.gameweeks[2]
    assert restored.players == hit_base.gameweeks[2].players
    assert restored.closing_bank_tenths == hit_base.gameweeks[2].closing_bank_tenths


def test_chip_gameweeks_use_ordinary_accounting_for_bench_boost_and_triple_captain() -> None:
    for chip in (Chip.BENCH_BOOST, Chip.TRIPLE_CAPTAIN):
        reference = plan(chips={9: chip})
        result = assess(reference, 9, 6, 106, evaluate_plan(reference, META))
        assert result.state == "available"
        assert result.resulting_bank_tenths == 12
        assert result.points_hit_after == 0


def test_a_later_sale_of_the_outgoing_player_blocks_with_a_structural_conflict() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "later_sale_of_a_player"
    )
    evaluation = evaluate_plan(reference, META)
    result = assess(reference, 8, 6, 106, evaluation)
    assert result.state == "blocked_by_later_decision"
    assert not result.confirmable
    conflict = result.conflict
    assert conflict is not None
    assert (conflict.kind, conflict.gameweek, conflict.code) == (
        "structural",
        10,
        "outgoing_not_owned",
    )
    assert conflict.decision_id == identity(2003)
    assert result.valid_through_gameweek == 9
    assert result.plan is not None
    assert result.plan.gameweeks[2].transfers == reference.gameweeks[2].transfers
    assert result.reasons == ()


def test_a_later_purchase_of_the_candidate_blocks_with_a_structural_conflict() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "later_purchase_of_a_candidate"
    )
    result = assess(reference, 8, 6, 107, evaluate_plan(reference, META))
    assert result.state == "blocked_by_later_decision"
    assert result.conflict is not None
    assert (result.conflict.kind, result.conflict.gameweek) == ("structural", 10)
    assert result.conflict.code == "incoming_already_owned"
    assert result.valid_through_gameweek == 9


def test_a_later_financial_shortfall_shows_values_through_that_gameweek_only() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "later_financial_chain"
    )
    result = assess(reference, 8, 6, 107, evaluate_plan(reference, META))
    assert result.state == "blocked_by_later_decision"
    conflict = result.conflict
    assert conflict is not None
    assert (conflict.kind, conflict.gameweek, conflict.code) == (
        "financial",
        10,
        "financial_shortfall",
    )
    assert conflict.shortfall_tenths == 5
    assert conflict.decision_id == identity(2007)
    assert result.valid_through_gameweek == 10
    assert result.resulting_bank_tenths == 10 + 52 - 59


def test_a_selected_gameweek_conflict_wins_over_a_later_one() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "later_financial_chain"
    )
    result = assess(reference, 8, 6, 108, evaluate_plan(reference, META))
    assert result.state == "unavailable"
    assert result.reasons == ("financial_shortfall",)
    assert result.conflict is not None and result.conflict.gameweek == 8
    assert result.valid_through_gameweek == 8


def test_a_squad_rule_breach_in_the_selected_gameweek_is_unavailable_with_the_rule_code() -> None:
    reference = plan()
    result = assess(reference, 8, 7, CLUB_LIMIT_CANDIDATE, evaluate_plan(reference, META))
    assert result.state == "unavailable"
    assert result.reasons == ("club_limit",)
    assert result.valid_through_gameweek == 7  # no squad exists in the gameweek itself
    assert result.plan is not None


def test_a_player_sold_by_another_transfer_in_the_gameweek_is_unavailable() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "candidate_sold_same_gameweek"
    )
    result = assess(reference, 9, 6, 7, evaluate_plan(reference, META))
    assert result.state == "unavailable"
    assert result.reasons == ("sold_this_gameweek",)
    assert result.plan is None and result.evaluation is None
    assert result.valid_through_gameweek == 8
    again = assess(reference, 9, 6, 109, evaluate_plan(reference, META))
    assert again.reasons != ("sold_this_gameweek",)


def test_an_existing_shortfall_does_not_block_a_candidate_that_does_not_worsen_it() -> None:
    reference = next(item.plan for item in reference_plans() if item.name == "existing_shortfall")
    evaluation = evaluate_plan(reference, META)
    assert evaluation.earliest_shortfall_gameweek == 8
    assert assess(reference, 9, 6, 106, evaluation).state == "available"
    assert assess(reference, 9, 6, 108, evaluation).state == "unavailable"


def test_assessing_every_candidate_leaves_inputs_unchanged() -> None:
    reference = next(
        item.plan for item in reference_plans() if item.name == "later_financial_chain"
    )
    evaluation = evaluate_plan(reference, META)
    plan_before, evaluation_before = copy.deepcopy(reference), copy.deepcopy(evaluation)
    for candidate in pool(evaluation, 8, 6):
        assess(reference, 8, 6, candidate, evaluation)
    assert reference == plan_before
    assert evaluation == evaluation_before


def test_hypothetical_identities_are_deterministic_and_distinct_per_candidate() -> None:
    reference = plan()
    evaluation = evaluate_plan(reference, META)
    first = assess(reference, 8, 6, 106, evaluation)
    second = assess(reference, 8, 6, 106, evaluation)
    other = assess(reference, 8, 6, 107, evaluation)
    assert first.decision == second.decision
    assert first.decision.decision_id != other.decision.decision_id
    assert first.decision.incoming_ownership_id != other.decision.incoming_ownership_id
    assert first.decision.incoming_ownership_id != identity(1006)


def test_every_transfer_gameweek_after_the_selected_one_is_left_untouched() -> None:
    reference = plan(transfers={10: (transfer(3, 103, 5),)})
    result = assess(reference, 8, 6, 106, evaluate_plan(reference, META))
    assert result.plan is not None
    assert result.plan.gameweeks[2] == reference.gameweeks[2]
    assert result.plan.gameweeks[3] == reference.gameweeks[3]
