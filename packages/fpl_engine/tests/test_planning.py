from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.models import (
    Boundary,
    GameweekDecision,
    Plan,
    PlayerRuleData,
    TransferDecision,
)
from fpl_engine.rules import RuleViolationError, SquadSlot, validate_squad

POSITIONS = (
    PlayerPosition.GOALKEEPER,
    *([PlayerPosition.DEFENDER] * 4),
    *([PlayerPosition.MIDFIELDER] * 4),
    *([PlayerPosition.FORWARD] * 2),
    PlayerPosition.GOALKEEPER,
    PlayerPosition.DEFENDER,
    PlayerPosition.MIDFIELDER,
    PlayerPosition.FORWARD,
)


def identity(number: int) -> UUID:
    return UUID(int=number)


def build_players() -> dict[int, SquadSlot]:
    players = {
        index + 1: SquadSlot(
            player_id=index + 1,
            position=position,
            team_id=index % 5 + 1,
            is_starting=index < 11,
            bench_order=None if index < 11 else index - 10,
            is_captain=index == 1,
            is_vice_captain=index == 2,
        )
        for index, position in enumerate(POSITIONS)
    }
    return players | {
        player_id + 100: replace(player, player_id=player_id + 100, team_id=20 + player_id)
        for player_id, player in players.items()
    }


def test_fixture_is_a_legal_multi_club_squad() -> None:
    players = build_players()
    validate_squad(list(players.values())[:15])
    assert len({player.team_id for player in list(players.values())[:15]}) == 5
    assert players[102].position == players[2].position
    assert identity(1) == UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize("value", range(6))
def test_starting_state_accepts_whole_remaining_transfers_including_zero(value: int) -> None:
    from fpl_engine.planning.models import SetStartingTransfers
    from fpl_engine.planning.mutations import apply_intents

    plan = build_plan(12, 13)
    assert plan.boundary.free_transfers == 1
    result = apply_intents(plan, (SetStartingTransfers(value),), metadata())
    assert result.plan.boundary.free_transfers == value
    assert result.evaluation.gameweeks[0].free_transfers_available == value
    assert result.evaluation.gameweeks[0].next_free_transfers == min(5, value + 1)


@pytest.mark.parametrize("value", [-1, 6, 1.5, True, None])
def test_starting_state_rejects_invalid_remaining_transfers(value: object) -> None:
    from fpl_engine.planning.models import SetStartingTransfers
    from fpl_engine.planning.mutations import apply_intents

    with pytest.raises(RuleViolationError):
        apply_intents(build_plan(12, 13), (SetStartingTransfers(value),), metadata())


@pytest.mark.parametrize("start", [1, 20])
def test_period_boundary_disallows_used_chips_and_gw1_requires_na(start: int) -> None:
    from fpl_engine.planning.models import SetStartingChips, SetStartingTransfers
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = build_plan(start, start + 1)
    if start == 1:
        plan = replace(plan, boundary=replace(plan.boundary, free_transfers=None))
        result = apply_intents(plan, (SetStartingTransfers(None),), metadata())
        assert result.evaluation.gameweeks[0].unlimited_transfers
        assert result.evaluation.gameweeks[1].free_transfers_available == 1
        with pytest.raises(RuleViolationError, match="N/A"):
            apply_intents(plan, (SetStartingTransfers(1),), metadata())
    for chip in Chip:
        with pytest.raises(RuleViolationError, match="No used chips"):
            apply_intents(plan, (SetStartingChips(frozenset({chip}), False),), metadata())


def test_starting_state_fh19_is_applicable_only_at_twenty() -> None:
    from fpl_engine.planning.models import SetStartingChips
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip
    from fpl_engine.rules.chips import chip_states

    result = apply_intents(build_plan(20, 21), (SetStartingChips(frozenset(), True),), metadata())
    assert result.plan.boundary.free_hit_gameweek_19
    state = chip_states(20, {}, start_gameweek=20, free_hit_gameweek_19=True)[Chip.FREE_HIT]
    assert state.state == "rule_unavailable"
    assert state.conflicting_gameweek == 19
    with pytest.raises(RuleViolationError, match="only applicable"):
        apply_intents(build_plan(25, 26), (SetStartingChips(frozenset(), True),), metadata())


def test_starting_state_used_chips_apply_to_the_starting_period_only() -> None:
    from fpl_engine.planning.models import SetStartingChips
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip
    from fpl_engine.rules.chips import chip_states

    for start in (12, 25):
        result = apply_intents(
            build_plan(start, start + 1),
            (SetStartingChips(frozenset({Chip.WILDCARD}), False),),
            metadata(),
        )
        states = chip_states(
            start, {}, start_gameweek=start, used_chips=result.plan.boundary.used_chips
        )
        assert states[Chip.WILDCARD].state == "used_before"
        if start == 12:
            assert (
                chip_states(
                    20, {}, start_gameweek=start, used_chips=result.plan.boundary.used_chips
                )[Chip.WILDCARD].state
                == "available"
            )


def test_contradictory_starting_chip_names_planned_gameweek_and_changes_nothing() -> None:
    from fpl_engine.planning.models import SetStartingChips
    from fpl_engine.planning.mutations import MutationRejectedError, apply_intents
    from fpl_engine.rules import Chip

    plan = with_week(build_plan(12, 19), 18, chip=Chip.WILDCARD)
    with pytest.raises(MutationRejectedError, match="Gameweek 18") as rejected:
        apply_intents(plan, (SetStartingChips(frozenset({Chip.WILDCARD}), False),), metadata())
    assert rejected.value.diagnostics[0].gameweek_number == 18
    assert plan.gameweeks[6].chip == Chip.WILDCARD
    assert not plan.boundary.used_chips


def build_boundary() -> Boundary:
    from fpl_engine.planning.models import Boundary, LineupRole, Ownership, PurchaseProvenance

    players = tuple(
        Ownership(
            slot_id=identity(player_id),
            ownership_id=identity(1000 + player_id),
            player_id=player_id,
            purchase_price_tenths=50,
            provenance=PurchaseProvenance("stored_player_observation", 50),
        )
        for player_id in range(1, 16)
    )
    lineup = tuple(
        LineupRole(
            identity(player.player_id),
            player.is_starting,
            player.bench_order,
            player.is_captain,
            player.is_vice_captain,
        )
        for player in list(build_players().values())[:15]
    )
    return Boundary(players, lineup, 10, 1)


def build_transfer(outgoing: int = 2, incoming: int = 102, number: int = 1) -> TransferDecision:
    from fpl_engine.planning.models import TransferDecision

    return TransferDecision(
        identity(2000 + number),
        outgoing,
        identity(1000 + outgoing),
        incoming,
        identity(3000 + number),
        54,
        50,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )


def test_boundary_contract_has_independent_stable_slots() -> None:
    boundary = build_boundary()
    assert len(boundary.players) == 15
    assert len({player.slot_id for player in boundary.players}) == 15
    assert boundary.players[0].provenance.confirmation == "assumed"
    with pytest.raises(RuleViolationError, match="15"):
        replace(boundary, players=boundary.players[:14])
    with pytest.raises(RuleViolationError):
        replace(boundary, players=(boundary.players[0],) + boundary.players[:-1])
    with pytest.raises(RuleViolationError):
        replace(boundary.players[0], slot_id="invalid")


@pytest.mark.parametrize("price", [0, -1, 5.5, True])
def test_price_inputs_must_be_positive_whole_tenths(price: object) -> None:
    with pytest.raises(RuleViolationError):
        replace(build_boundary().players[0], purchase_price_tenths=price)


def test_net_set_rejects_duplicate_changes_and_round_trips() -> None:
    from fpl_engine.planning.models import GameweekDecision

    boundary = build_boundary()
    transfer = build_transfer()
    with pytest.raises(RuleViolationError):
        GameweekDecision(8, boundary.lineup, (transfer, transfer))
    with pytest.raises(RuleViolationError):
        GameweekDecision(8, boundary.lineup, (transfer, build_transfer(102, 2, 2)))


def test_planned_acquisition_provenance_is_not_an_estimated_historical_purchase() -> None:
    from fpl_engine.planning.models import PurchaseProvenance

    provenance = PurchaseProvenance("decision:example", 52, "planned_acquisition", None)
    assert provenance.confirmation is None
    assert provenance.original_price_tenths == 52
    with pytest.raises(RuleViolationError):
        replace(provenance, confirmation="assumed")


@pytest.mark.parametrize(
    ("market", "sale"), [(48, 48), (50, 50), (51, 50), (52, 51), (53, 51), (54, 52)]
)
def test_official_sale_steps(market: int, sale: int) -> None:
    from fpl_engine.planning.prices import selling_price_tenths

    assert selling_price_tenths(50, market) == sale


def build_plan(start: int = 8, end: int = 11) -> Plan:
    boundary = build_boundary()
    return Plan(
        "Test plan",
        start,
        end,
        boundary,
        tuple(GameweekDecision(number, boundary.lineup) for number in range(start, end + 1)),
    )


def metadata() -> dict[int, PlayerRuleData]:
    return {
        player_id: PlayerRuleData(player_id, player.position, player.team_id)
        for player_id, player in build_players().items()
    }


def with_week(plan: Plan, number: int, **changes) -> Plan:
    return replace(
        plan,
        gameweeks=tuple(
            replace(week, **changes) if week.gameweek_number == number else week
            for week in plan.gameweeks
        ),
    )


def test_us3_hand_calculated_chain_and_unordered_net_set_preserve_local_roles() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan

    plan = build_plan(8, 12)
    plan = replace(plan, boundary=replace(plan.boundary, free_transfers=2))
    plan = with_week(plan, 8, transfers=(build_transfer(),))
    transfers = tuple(build_transfer(player, player + 100, player) for player in (3, 4, 5, 6))
    plan = with_week(plan, 10, transfers=transfers)
    lineup = tuple(
        replace(
            role,
            is_captain=role.slot_id == identity(3),
            is_vice_captain=role.slot_id == identity(2),
        )
        for role in plan.gameweeks[3].lineup
    )
    plan = with_week(plan, 11, lineup=lineup)
    result = evaluate_plan(plan, metadata())
    assert not result.diagnostics
    assert [
        (
            week.free_transfers_available,
            week.transfers_made,
            week.points_hit,
            week.next_free_transfers,
            week.closing_bank_tenths,
        )
        for week in result.gameweeks
    ] == [
        (2, 1, 0, 2, 12),
        (2, 0, 0, 3, 12),
        (3, 4, 4, 1, 20),
        (1, 0, 0, 2, 20),
        (2, 0, 0, 3, 20),
    ]
    assert sum(week.points_hit for week in result.gameweeks) == 4
    assert result.gameweeks[3].lineup == lineup
    assert result.gameweeks[4].lineup == plan.boundary.lineup
    assert (
        evaluate_plan(with_week(plan, 10, transfers=tuple(reversed(transfers))), metadata())
        == result
    )


@pytest.mark.parametrize("remaining", range(6))
@pytest.mark.parametrize(
    "chip_name", [None, "WILDCARD", "FREE_HIT", "BENCH_BOOST", "TRIPLE_CAPTAIN"]
)
def test_us3_allowance_hits_and_cap_matrix(remaining, chip_name) -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    chip = Chip(chip_name) if chip_name else None
    for count in (0, 1, 4):
        plan = build_plan()
        plan = replace(plan, boundary=replace(plan.boundary, free_transfers=remaining))
        decisions = tuple(
            build_transfer(player, player + 100, player) for player in range(2, 2 + count)
        )
        plan = with_week(plan, 8, chip=chip, transfers=decisions)
        result = evaluate_plan(plan, metadata())
        assert not result.diagnostics
        unlimited = chip_name in {"WILDCARD", "FREE_HIT"}
        expected_next = min(5, max(remaining - (1 if unlimited else count), 0) + 1)
        assert (
            result.gameweeks[0].transfers_made,
            result.gameweeks[0].points_hit,
            result.gameweeks[0].next_free_transfers,
        ) == (count, 0 if unlimited else max(count - remaining, 0) * 4, expected_next)
        assert result.gameweeks[1].closing_bank_tenths == (
            10 if chip_name == "FREE_HIT" else 10 + count * 2
        )


@pytest.mark.parametrize("first_chip", ["FREE_HIT", "WILDCARD"])
def test_us3_adjacent_first_last_chips_and_buy_back_episode(first_chip) -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    first = build_transfer()
    plan = with_week(build_plan(8, 9), 8, chip=Chip(first_chip), transfers=(first,))
    if first_chip == "FREE_HIT":
        second = replace(build_transfer(2, 102, 2), outgoing_ownership_id=identity(1002))
    else:
        second = replace(
            build_transfer(102, 2, 2), outgoing_ownership_id=first.incoming_ownership_id
        )
    plan = with_week(
        plan,
        9,
        chip=Chip.WILDCARD if first_chip == "FREE_HIT" else Chip.FREE_HIT,
        transfers=(second,),
    )
    result = evaluate_plan(plan, metadata())
    assert not result.diagnostics
    assert result.gameweeks[1].players[1].ownership_id == second.incoming_ownership_id
    assert result.gameweeks[1].players[1].ownership_id != first.outgoing_ownership_id
    assert plan.gameweeks[0].transfers == (first,)
    assert result.gameweeks[1].points_hit == 0


def test_us3_example_b_explicit_replacement_is_atomic_and_preserves_unchanged_quotes() -> None:
    from fpl_engine.planning.models import EditTransfer
    from fpl_engine.planning.mutations import apply_intents

    first = build_transfer()
    later = replace(build_transfer(102, 2, 2), outgoing_ownership_id=first.incoming_ownership_id)
    plan = with_week(with_week(build_plan(), 8, transfers=(first,)), 10, transfers=(later,))
    changed = replace(first, incoming_player_id=103, incoming_ownership_id=identity(4001))
    replacement = replace(
        later, outgoing_player_id=103, outgoing_ownership_id=changed.incoming_ownership_id
    )
    result = apply_intents(
        plan,
        (EditTransfer(first.decision_id, changed), EditTransfer(later.decision_id, replacement)),
        metadata(),
    )
    assert not result.evaluation.diagnostics
    assert result.plan.gameweeks[2].transfers == (replacement,)
    assert result.plan.gameweeks[0].transfers == (changed,)
    assert plan.gameweeks[0].transfers == (first,)


def test_first_gameweek_counts_against_independent_boundary_with_zero_ft() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan

    plan = build_plan()
    plan = replace(plan, boundary=replace(plan.boundary, free_transfers=0))
    plan = with_week(plan, 8, transfers=(build_transfer(),))
    result = evaluate_plan(plan, metadata())
    assert not result.diagnostics
    week = result.gameweeks[0]
    assert (week.transfers_made, week.points_hit, week.next_free_transfers) == (1, 4, 1)
    assert week.closing_bank_tenths == 12
    assert week.sales[0].selling_price_tenths == 52


def test_us3_permanent_buy_back_requires_the_new_episode_and_forbids_same_week_round_trip() -> None:
    from fpl_engine.planning.mutations import AddTransfer, MutationRejectedError, apply_intents

    first = build_transfer()
    second = replace(build_transfer(102, 2, 2), outgoing_ownership_id=first.incoming_ownership_id)
    third = replace(build_transfer(2, 103, 3), outgoing_ownership_id=second.incoming_ownership_id)
    plan = with_week(with_week(build_plan(), 8, transfers=(first,)), 9, transfers=(second,))
    result = apply_intents(plan, (AddTransfer(10, third),), metadata())
    assert result.plan.gameweeks[2].transfers == (third,)
    assert second.incoming_ownership_id != identity(1002)
    with pytest.raises(MutationRejectedError):
        apply_intents(
            plan,
            (AddTransfer(10, replace(third, outgoing_ownership_id=identity(1002))),),
            metadata(),
        )
    with pytest.raises(RuleViolationError):
        apply_intents(build_plan(), (AddTransfer(8, first), AddTransfer(8, second)), metadata())


def test_example_a_free_hit_restores_permanent_ownership_without_phantom_transfers() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    plan = with_week(build_plan(), 8, transfers=(build_transfer(),))
    ordinary = evaluate_plan(plan, metadata())
    temporary = evaluate_plan(with_week(plan, 8, chip=Chip.FREE_HIT), metadata())
    assert not temporary.diagnostics
    assert ordinary.gameweeks[1].players[1].player_id == 102
    assert temporary.gameweeks[0].players[1].player_id == 102
    assert temporary.gameweeks[1].players == plan.boundary.players
    assert temporary.gameweeks[1].closing_bank_tenths == 10
    assert temporary.gameweeks[1].transfers_made == 0
    assert temporary.gameweeks[1].lineup == plan.gameweeks[1].lineup


def test_example_b_missing_ownership_blocks_accounting_instead_of_retargeting() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan

    first = build_transfer()
    later = replace(build_transfer(102, 2, 2), outgoing_ownership_id=first.incoming_ownership_id)
    plan = with_week(with_week(build_plan(), 8, transfers=(first,)), 10, transfers=(later,))
    assert not evaluate_plan(plan, metadata()).diagnostics
    changed = with_week(plan, 8, transfers=(replace(first, incoming_player_id=103),))
    result = evaluate_plan(changed, metadata())
    assert any(
        error.code == "outgoing_not_owned" and error.decision_id == later.decision_id
        for error in result.diagnostics
    )
    assert result.gameweeks[2].closing_bank_tenths is None
    assert result.gameweeks[3].transfers_made is None
    assert result.gameweeks[3].shortfall_tenths is None


def test_wildcard_retains_existing_basis_and_makes_new_acquisitions_permanent() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    plan = with_week(build_plan(), 8, chip=Chip.WILDCARD, transfers=(build_transfer(),))
    result = evaluate_plan(plan, metadata())
    assert result.gameweeks[1].players[0] == plan.boundary.players[0]
    assert result.gameweeks[1].players[1].provenance.basis_kind == "planned_acquisition"
    assert result.gameweeks[1].players[1].ownership_id == identity(3001)


def test_saved_market_correction_replays_negative_banks_without_repricing_incoming() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan

    transfer = replace(build_transfer(), incoming_price_tenths=62)
    plan = with_week(build_plan(), 8, transfers=(transfer,))
    before = evaluate_plan(plan, metadata())
    corrected_players = tuple(
        replace(player, purchase_price_tenths=48) if player.player_id == 2 else player
        for player in plan.boundary.players
    )
    after = evaluate_plan(
        replace(plan, boundary=replace(plan.boundary, players=corrected_players)), metadata()
    )
    assert before.gameweeks[0].closing_bank_tenths == 0
    assert after.gameweeks[0].closing_bank_tenths == -1
    assert after.gameweeks[0].sales[0].selling_price_tenths == 51
    assert after.earliest_shortfall_gameweek == 8
    assert after.gameweeks[1].financial_issue_gameweeks == frozenset({8, 9})
    assert plan.gameweeks[0].transfers[0].incoming_price_tenths == 62


def test_temporary_financial_issue_does_not_leak_into_restored_bank() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    plan = with_week(
        build_plan(),
        8,
        chip=Chip.FREE_HIT,
        transfers=(replace(build_transfer(), incoming_price_tenths=63),),
    )
    result = evaluate_plan(plan, metadata())
    assert result.gameweeks[0].closing_bank_tenths == -1
    assert result.gameweeks[1].closing_bank_tenths == 10
    assert result.gameweeks[1].financial_issue_gameweeks == frozenset()
    assert result.earliest_shortfall_gameweek == 8


def test_q7_correction_is_accepted_but_cannot_exempt_a_mixed_planning_batch() -> None:
    from fpl_engine.planning.models import CorrectPurchasePrice, RenamePlan
    from fpl_engine.planning.mutations import apply_intents

    plan = with_week(
        build_plan(), 8, transfers=(replace(build_transfer(), incoming_price_tenths=62),)
    )
    correction = CorrectPurchasePrice(identity(1002), 48)
    result = apply_intents(plan, (correction,), metadata())
    assert result.evaluation.gameweeks[0].closing_bank_tenths == -1
    assert result.plan.boundary.players[1].provenance.original_price_tenths == 50
    assert result.plan.boundary.players[1].provenance.confirmation == "user_confirmed"
    assert result.plan.gameweeks == plan.gameweeks
    with pytest.raises(RuleViolationError, match="mix"):
        apply_intents(plan, (correction, RenamePlan("Other")), metadata())


def test_example_b_rejects_upstream_alone_and_accepts_explicit_atomic_removal() -> None:
    from fpl_engine.planning.models import EditTransfer, RemoveTransfer
    from fpl_engine.planning.mutations import apply_intents

    first = build_transfer()
    later = replace(build_transfer(102, 2, 2), outgoing_ownership_id=first.incoming_ownership_id)
    plan = with_week(with_week(build_plan(), 8, transfers=(first,)), 10, transfers=(later,))
    edit = EditTransfer(
        first.decision_id,
        replace(first, incoming_player_id=103, incoming_ownership_id=identity(4001)),
    )
    with pytest.raises(RuleViolationError, match="Gameweek 10"):
        apply_intents(plan, (edit,), metadata())
    repaired = apply_intents(plan, (edit, RemoveTransfer(later.decision_id)), metadata())
    assert not repaired.evaluation.diagnostics
    assert repaired.evaluation.gameweeks[2].transfers_made == 0


def test_one_independent_legacy_ownership_error_can_be_repaired_while_another_remains() -> None:
    from fpl_engine.planning.models import AddTransfer, RemoveTransfer
    from fpl_engine.planning.mutations import apply_intents

    first = replace(build_transfer(), outgoing_ownership_id=identity(9000))
    second = replace(build_transfer(3, 103, 2), outgoing_ownership_id=identity(9001))
    plan = with_week(build_plan(), 8, transfers=(first, second))
    repaired = apply_intents(plan, (RemoveTransfer(first.decision_id),), metadata())
    assert any(error.decision_id == second.decision_id for error in repaired.evaluation.diagnostics)
    assert repaired.evaluation.gameweeks[1].closing_bank_tenths is None
    assert repaired.evaluation.gameweeks[1].shortfall_tenths is None
    with pytest.raises(RuleViolationError):
        apply_intents(plan, (AddTransfer(10, build_transfer(4, 104, 3)),), metadata())


def test_financial_comparison_accepts_moving_the_earliest_failure_later() -> None:
    from fpl_engine.planning.models import EditTransfer
    from fpl_engine.planning.mutations import apply_intents

    first = replace(build_transfer(), incoming_price_tenths=63)
    second = replace(build_transfer(3, 103, 2), incoming_price_tenths=54)
    plan = with_week(with_week(build_plan(), 9, transfers=(first,)), 10, transfers=(second,))
    result = apply_intents(
        plan,
        (EditTransfer(first.decision_id, replace(first, incoming_price_tenths=62)),),
        metadata(),
    )
    assert [week.closing_bank_tenths for week in result.evaluation.gameweeks[1:3]] == [0, -2]
    assert result.evaluation.earliest_shortfall_gameweek == 10
    with pytest.raises(RuleViolationError):
        apply_intents(
            plan,
            (EditTransfer(first.decision_id, replace(first, incoming_price_tenths=64)),),
            metadata(),
        )


def test_horizon_rebase_preserves_permanent_state_provenance_quotes_and_editability() -> None:
    from fpl_engine.planning.models import ChangeHorizon, CorrectPurchasePrice
    from fpl_engine.planning.mutations import apply_intents

    first = build_transfer()
    later = replace(build_transfer(102, 2, 2), outgoing_ownership_id=first.incoming_ownership_id)
    plan = with_week(with_week(build_plan(), 8, transfers=(first,)), 10, transfers=(later,))
    rebased = apply_intents(plan, (ChangeHorizon(9, 12),), metadata()).plan
    assert rebased.boundary.bank_tenths == 12
    assert rebased.boundary.players[1].ownership_id == first.incoming_ownership_id
    assert rebased.boundary.players[1].provenance.basis_kind == "planned_acquisition"
    assert str(first.decision_id) in rebased.boundary.players[1].provenance.source
    assert rebased.gameweeks[1].transfers == (later,)
    corrected = apply_intents(
        rebased, (CorrectPurchasePrice(first.incoming_ownership_id, 48),), metadata()
    )
    assert corrected.plan.boundary.bank_tenths == 12
    assert corrected.plan.boundary.players[1].provenance.original_price_tenths == 50
    assert corrected.plan.boundary.players[1].provenance.confirmation is None
    assert corrected.evaluation.gameweeks[1].sales[0].selling_price_tenths == 51


def test_horizon_rejects_unresolved_prefix_and_extends_after_final_free_hit_permanently() -> None:
    from fpl_engine.planning.models import ChangeHorizon
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = with_week(build_plan(8, 8), 8, chip=Chip.FREE_HIT, transfers=(build_transfer(),))
    extended = apply_intents(plan, (ChangeHorizon(8, 9),), metadata())
    assert extended.evaluation.gameweeks[1].players == plan.boundary.players
    assert extended.evaluation.gameweeks[1].closing_bank_tenths == 10
    invalid = with_week(
        build_plan(), 8, transfers=(replace(build_transfer(), incoming_price_tenths=63),)
    )
    with pytest.raises(RuleViolationError):
        apply_intents(invalid, (ChangeHorizon(9, 11),), metadata())


def test_chip_reasons_distinguish_used_before_planned_elsewhere_and_boundary_rules() -> None:
    from fpl_engine.rules.chips import Chip, chip_states

    states = chip_states(
        12, {14: Chip.WILDCARD}, start_gameweek=12, used_chips=frozenset({Chip.FREE_HIT})
    )
    assert states[Chip.WILDCARD].state == "planned_elsewhere"
    assert states[Chip.WILDCARD].conflicting_gameweek == 14
    assert states[Chip.FREE_HIT].state == "used_before"
    assert (
        chip_states(20, {}, start_gameweek=12, used_chips=frozenset({Chip.FREE_HIT}))[
            Chip.FREE_HIT
        ].state
        == "available"
    )
    assert chip_states(1, {}, start_gameweek=1)[Chip.WILDCARD].state == "rule_unavailable"
    assert (
        chip_states(20, {}, start_gameweek=20, free_hit_gameweek_19=True)[
            Chip.FREE_HIT
        ].conflicting_gameweek
        == 19
    )


def test_finishing_a_legacy_repair_reestablishes_verified_accounting() -> None:
    from fpl_engine.planning.models import RemoveTransfer
    from fpl_engine.planning.mutations import apply_intents

    broken = replace(build_transfer(), outgoing_ownership_id=identity(9000))
    plan = with_week(build_plan(), 8, transfers=(broken,))
    result = apply_intents(plan, (RemoveTransfer(broken.decision_id),), metadata())
    assert not result.evaluation.diagnostics
    assert result.evaluation.gameweeks[1].closing_bank_tenths == 10


def test_core_chip_activate_move_remove_and_local_captain_intents_preserve_quotes() -> None:
    from fpl_engine.planning.models import ChangeCaptain, MoveChip, SetChip
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = with_week(build_plan(), 8, transfers=(build_transfer(),))
    active = apply_intents(plan, (SetChip(8, Chip.FREE_HIT, None),), metadata()).plan
    moved = apply_intents(active, (MoveChip(8, 9, Chip.FREE_HIT),), metadata()).plan
    removed = apply_intents(moved, (SetChip(9, None, Chip.FREE_HIT),), metadata()).plan
    assert removed == plan
    captain = apply_intents(plan, (ChangeCaptain(8, 4),), metadata()).plan
    assert captain.gameweeks[0].transfers == plan.gameweeks[0].transfers
    assert captain.gameweeks[1].lineup == plan.gameweeks[1].lineup


def test_core_hypothetical_earlier_start_and_trim_preserve_retained_decisions() -> None:
    from fpl_engine.planning.models import ChangeHorizon
    from fpl_engine.planning.mutations import apply_intents

    plan = with_week(build_plan(), 8, transfers=(build_transfer(),))
    changed = apply_intents(plan, (ChangeHorizon(7, 10),), metadata()).plan
    assert changed.boundary.origin == "earlier_horizon_assumed"
    assert changed.gameweeks[0].transfers == ()
    assert changed.gameweeks[1:] == plan.gameweeks[:3]


@pytest.mark.parametrize(
    ("start", "target", "expected_used"),
    [
        (25, 19, False),
        (25, 20, False),
        (12, 1, False),
        (25, 24, True),
        (12, 11, True),
        (18, 25, False),
    ],
)
def test_horizon_defaults_do_not_reinterpret_chip_period_history(
    start: int, target: int, expected_used: bool
) -> None:
    from fpl_engine.planning.models import ChangeHorizon
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = build_plan(start, 26)
    plan = replace(plan, boundary=replace(plan.boundary, used_chips=frozenset({Chip.WILDCARD})))
    changed = apply_intents(plan, (ChangeHorizon(target, 26),), metadata()).plan
    assert changed.boundary.used_chips == (
        frozenset({Chip.WILDCARD}) if expected_used else frozenset()
    )
    assert all(week.chip is None for week in changed.gameweeks)


def test_earlier_start_drops_fh19_declaration_without_inventing_a_decision() -> None:
    from fpl_engine.planning.models import ChangeHorizon
    from fpl_engine.planning.mutations import apply_intents

    plan = build_plan(20, 21)
    plan = replace(plan, boundary=replace(plan.boundary, free_hit_gameweek_19=True))
    changed = apply_intents(plan, (ChangeHorizon(19, 21),), metadata()).plan
    assert not changed.boundary.free_hit_gameweek_19
    assert changed.gameweeks[0].chip is None


def test_earlier_hypothetical_boundary_preserves_zero_free_transfers() -> None:
    from fpl_engine.planning.models import ChangeHorizon
    from fpl_engine.planning.mutations import apply_intents

    plan = build_plan()
    plan = replace(plan, boundary=replace(plan.boundary, free_transfers=0))
    result = apply_intents(plan, (ChangeHorizon(7, 10),), metadata())
    assert result.plan.boundary.free_transfers == 0
    assert result.evaluation.gameweeks[0].free_transfers_available == 0


def test_core_add_edit_remove_and_confirmation_are_field_scoped() -> None:
    from fpl_engine.planning.models import (
        AddTransfer,
        ConfirmPurchasePrice,
        EditTransfer,
        RemoveTransfer,
    )
    from fpl_engine.planning.mutations import apply_intents

    plan = build_plan()
    decision = build_transfer()
    added = apply_intents(plan, (AddTransfer(8, decision),), metadata()).plan
    edited = replace(decision, incoming_price_tenths=52)
    changed = apply_intents(added, (EditTransfer(decision.decision_id, edited),), metadata())
    assert changed.evaluation.gameweeks[0].closing_bank_tenths == 10
    assert changed.plan.gameweeks[0].transfers == (edited,)
    removed = apply_intents(changed.plan, (RemoveTransfer(decision.decision_id),), metadata()).plan
    assert removed == plan
    ownership = plan.boundary.players[0]
    confirmed = apply_intents(plan, (ConfirmPurchasePrice(ownership.ownership_id),), metadata())
    assert confirmed.plan.boundary.bank_tenths == 10
    assert confirmed.plan.boundary.players[0].provenance.source == ownership.provenance.source
    assert confirmed.plan.boundary.players[0].provenance.confirmation == "user_confirmed"
    assert confirmed.evaluation.gameweeks[0].closing_bank_tenths == 10


def test_core_rebase_carries_free_hit_19_without_second_period_chip_use() -> None:
    from fpl_engine.planning.models import ChangeHorizon
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = with_week(build_plan(18, 21), 19, chip=Chip.FREE_HIT)
    result = apply_intents(plan, (ChangeHorizon(20, 21),), metadata())
    assert result.plan.boundary.free_hit_gameweek_19
    assert not result.plan.boundary.used_chips
    assert result.plan.boundary.bank_tenths == 10
    assert result.plan.gameweeks == plan.gameweeks[2:]


def test_repair_one_legacy_lineup_without_fabricating_other_blocked_accounting() -> None:
    from fpl_engine.planning.models import ChangeCaptain
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = build_plan()
    bad = tuple(replace(role, is_captain=role.is_vice_captain) for role in plan.boundary.lineup)
    plan = with_week(with_week(plan, 8, chip=Chip.FREE_HIT, lineup=bad), 9, lineup=bad)
    captain = next(
        player.player_id
        for player, role in zip(plan.boundary.players, plan.boundary.lineup, strict=True)
        if role.is_captain
    )
    repaired = apply_intents(plan, (ChangeCaptain(8, captain),), metadata())
    assert not any(error.gameweek_number == 8 for error in repaired.evaluation.diagnostics)
    assert any(error.gameweek_number == 9 for error in repaired.evaluation.diagnostics)
    assert repaired.evaluation.gameweeks[0].closing_bank_tenths == 10
    assert repaired.evaluation.gameweeks[1].closing_bank_tenths is None
    assert repaired.evaluation.gameweeks[2].shortfall_tenths is None


def test_legal_rearrangements_are_executable_domain_intents() -> None:
    from fpl_engine.planning.models import SwapLineupPlayers
    from fpl_engine.planning.mutations import apply_intents, legal_rearrangements

    plan = build_plan()
    choices = legal_rearrangements(plan, 8, metadata())
    assert choices
    for choice in choices:
        assert not apply_intents(
            plan,
            (
                SwapLineupPlayers(
                    8, int(choice["first_player_id"]), int(choice["second_player_id"])
                ),
            ),
            metadata(),
        ).evaluation.diagnostics


@pytest.mark.parametrize(
    ("market", "sale"), [(40, 40), (48, 48), (50, 50), (51, 50), (52, 51), (53, 51), (54, 52)]
)
def test_us4_replay_sales_and_bank_use_saved_market_not_incoming_or_live(
    market: int, sale: int
) -> None:
    from fpl_engine.planning.evaluate import evaluate_plan

    plan = with_week(
        build_plan(), 8, transfers=(replace(build_transfer(), outgoing_market_tenths=market),)
    )
    week = evaluate_plan(plan, metadata()).gameweeks[0]
    assert week.sales[0].selling_price_tenths == sale
    assert week.closing_bank_tenths == 10 + sale - 50
    assert week.provisional_dependencies >= {identity(1002)}


def test_us4_wildcard_acquisition_basis_carries_to_a_later_buy_back_chain() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    first = replace(build_transfer(), incoming_price_tenths=52)
    second = replace(
        build_transfer(102, 2, 2),
        outgoing_ownership_id=identity(3001),
        outgoing_market_tenths=56,
    )
    third = replace(
        build_transfer(2, 103, 3), outgoing_ownership_id=identity(3002), outgoing_market_tenths=53
    )
    plan = with_week(build_plan(8, 10), 8, chip=Chip.WILDCARD, transfers=(first,))
    plan = with_week(with_week(plan, 9, transfers=(second,)), 10, transfers=(third,))
    result = evaluate_plan(plan, metadata())
    assert not result.diagnostics
    # WC sale 52 (50/54) funds the 52 acquisition; its saved 52 is the new basis.
    assert [week.sales[0].selling_price_tenths for week in result.gameweeks] == [52, 54, 51]
    assert [week.closing_bank_tenths for week in result.gameweeks] == [10, 14, 15]
    assert [week.points_hit for week in result.gameweeks] == [0, 0, 0]
    bought_back = result.gameweeks[1].players[1]
    assert (bought_back.player_id, bought_back.purchase_price_tenths) == (2, 50)
    assert bought_back.ownership_id == identity(3002) != identity(1002)


def test_us4_free_hit_sales_are_temporary_and_new_sales_use_latest_assumption() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    saved = replace(build_transfer(), outgoing_market_tenths=52, incoming_price_tenths=53)
    later = replace(build_transfer(2, 103, 2), outgoing_market_tenths=54)
    plan = with_week(build_plan(8, 9), 8, chip=Chip.FREE_HIT, transfers=(saved,))
    plan = with_week(plan, 9, transfers=(later,))
    result = evaluate_plan(plan, metadata())
    assert not result.diagnostics
    temporary, restored = result.gameweeks
    assert temporary.sales[0].selling_price_tenths == 51
    assert temporary.closing_bank_tenths == 8
    assert restored.starting_bank_tenths == 10
    assert restored.sales[0].selling_price_tenths == 52
    assert restored.closing_bank_tenths == 12
    assert plan.gameweeks[0].transfers == (saved,)


def test_us4_upstream_acquisition_edit_reprices_dependent_sale_from_its_own_saved_market() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import EditTransfer
    from fpl_engine.planning.mutations import MutationRejectedError, apply_intents

    first = build_transfer()
    later = replace(
        build_transfer(102, 2, 2),
        outgoing_ownership_id=first.incoming_ownership_id,
        outgoing_market_tenths=56,
    )
    plan = with_week(with_week(build_plan(), 8, transfers=(first,)), 10, transfers=(later,))
    before = evaluate_plan(plan, metadata())
    assert (
        before.gameweeks[2].sales[0].selling_price_tenths,
        before.gameweeks[2].closing_bank_tenths,
    ) == (53, 15)
    result = apply_intents(
        plan,
        (EditTransfer(first.decision_id, replace(first, incoming_price_tenths=54)),),
        metadata(),
    )
    after = result.evaluation
    assert after.gameweeks[0].closing_bank_tenths == 8
    assert (
        after.gameweeks[2].sales[0].selling_price_tenths,
        after.gameweeks[2].closing_bank_tenths,
    ) == (55, 13)
    assert result.plan.gameweeks[2].transfers == (later,)
    with pytest.raises(MutationRejectedError, match="Gameweek 8"):
        apply_intents(
            plan,
            (EditTransfer(first.decision_id, replace(first, incoming_price_tenths=63)),),
            metadata(),
        )


def test_us4_confirmation_changes_no_money_and_clears_only_that_dependency() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import ConfirmPurchasePrice
    from fpl_engine.planning.mutations import apply_intents

    plan = with_week(build_plan(), 8, transfers=(build_transfer(),))
    before = evaluate_plan(plan, metadata()).gameweeks[0]
    result = apply_intents(plan, (ConfirmPurchasePrice(identity(1002)),), metadata())
    after = result.evaluation.gameweeks[0]
    confirmed = next(p for p in result.plan.boundary.players if p.player_id == 2)
    assert (confirmed.provenance.confirmation, confirmed.provenance.source) == (
        "user_confirmed",
        "stored_player_observation",
    )
    assert after.closing_bank_tenths == before.closing_bank_tenths
    assert [(s.decision_id, s.selling_price_tenths) for s in after.sales] == [
        (s.decision_id, s.selling_price_tenths) for s in before.sales
    ]
    assert identity(1002) in before.provisional_dependencies
    assert identity(1002) not in after.provisional_dependencies
    assert identity(1001) in after.provisional_dependencies


def test_us4_provisional_bank_dependency_survives_sale_but_not_a_free_hit_branch() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.rules import Chip

    sold = build_transfer(3, 103, 1)
    ordinary = evaluate_plan(with_week(build_plan(8, 9), 8, transfers=(sold,)), metadata())
    assert identity(1003) in ordinary.gameweeks[1].provisional_dependencies
    assert identity(1003) not in {p.ownership_id for p in ordinary.gameweeks[1].players}
    free_hit = evaluate_plan(
        with_week(build_plan(8, 9), 8, chip=Chip.FREE_HIT, transfers=(sold,)), metadata()
    )
    assert identity(1003) in free_hit.gameweeks[0].provisional_dependencies
    assert identity(1003) not in free_hit.gameweeks[0].permanent_bank_dependencies


def test_us4_correction_deficit_survives_later_positive_bank_and_clears_after_repair() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import CorrectPurchasePrice, EditTransfer
    from fpl_engine.planning.mutations import apply_intents

    first = replace(build_transfer(), incoming_price_tenths=62)
    second = replace(build_transfer(3, 103, 2), outgoing_market_tenths=54)
    plan = with_week(with_week(build_plan(8, 10), 8, transfers=(first,)), 9, transfers=(second,))
    assert not evaluate_plan(plan, metadata()).earliest_shortfall_gameweek
    corrected = apply_intents(plan, (CorrectPurchasePrice(identity(1002), 48),), metadata())
    weeks = corrected.evaluation.gameweeks
    assert [week.closing_bank_tenths for week in weeks] == [-1, 1, 1]
    assert corrected.evaluation.earliest_shortfall_gameweek == 8
    assert weeks[1].shortfall_tenths == 0
    assert weeks[1].financial_issue_gameweeks == frozenset({8})
    assert corrected.plan.gameweeks == plan.gameweeks
    repaired = apply_intents(
        corrected.plan,
        (EditTransfer(first.decision_id, replace(first, incoming_price_tenths=61)),),
        metadata(),
    )
    assert repaired.evaluation.earliest_shortfall_gameweek is None
    assert all(not week.financial_issue_gameweeks for week in repaired.evaluation.gameweeks)


def test_us4_correction_reprices_temporary_and_later_permanent_sales_from_each_saved_market() -> (
    None
):
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import CorrectPurchasePrice
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    temporary = replace(build_transfer(), incoming_price_tenths=62)
    permanent = replace(build_transfer(2, 103, 2), outgoing_market_tenths=52)
    plan = with_week(build_plan(8, 9), 8, chip=Chip.FREE_HIT, transfers=(temporary,))
    plan = with_week(plan, 9, transfers=(permanent,))
    before = evaluate_plan(plan, metadata())
    assert [w.closing_bank_tenths for w in before.gameweeks] == [0, 11]
    corrected = apply_intents(plan, (CorrectPurchasePrice(identity(1002), 48),), metadata())
    weeks = corrected.evaluation.gameweeks
    assert [w.sales[0].selling_price_tenths for w in weeks] == [51, 50]
    assert [w.closing_bank_tenths for w in weeks] == [-1, 10]
    assert corrected.evaluation.earliest_shortfall_gameweek == 8
    assert weeks[1].starting_bank_tenths == 10
    assert weeks[1].financial_issue_gameweeks == frozenset()
    assert corrected.plan.gameweeks == plan.gameweeks


def test_us4_permanent_deficit_stays_dependent_through_a_free_hit_week() -> None:
    from fpl_engine.planning.models import CorrectPurchasePrice
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    plan = with_week(
        build_plan(8, 10), 8, transfers=(replace(build_transfer(), incoming_price_tenths=62),)
    )
    plan = with_week(plan, 9, chip=Chip.FREE_HIT)
    corrected = apply_intents(plan, (CorrectPurchasePrice(identity(1002), 48),), metadata())
    weeks = corrected.evaluation.gameweeks
    assert [w.closing_bank_tenths for w in weeks] == [-1, -1, -1]
    # The FH week is itself negative, but its temporary issue must not reach GW10.
    assert [w.financial_issue_gameweeks for w in weeks] == [
        frozenset({8}),
        frozenset({8, 9}),
        frozenset({8, 10}),
    ]
    assert corrected.evaluation.earliest_shortfall_gameweek == 8


def test_us4_sale_exposes_the_basis_and_provenance_that_produced_it() -> None:
    from fpl_engine.planning.evaluate import evaluate_plan
    from fpl_engine.planning.models import ConfirmPurchasePrice, CorrectPurchasePrice
    from fpl_engine.planning.mutations import apply_intents
    from fpl_engine.rules import Chip

    first = replace(build_transfer(), incoming_price_tenths=52)
    second = replace(
        build_transfer(102, 2, 2),
        outgoing_ownership_id=identity(3001),
        outgoing_market_tenths=56,
    )
    plan = with_week(build_plan(8, 9), 8, chip=Chip.WILDCARD, transfers=(first,))
    plan = with_week(plan, 9, transfers=(second,))
    starting, acquired = (
        evaluate_plan(plan, metadata()).gameweeks[0].sales[0],
        evaluate_plan(plan, metadata()).gameweeks[1].sales[0],
    )
    assert (starting.purchase_price_tenths, starting.basis_kind, starting.basis_confirmation) == (
        50,
        "starting",
        "assumed",
    )
    assert (acquired.purchase_price_tenths, acquired.basis_kind, acquired.basis_confirmation) == (
        52,
        "planned_acquisition",
        None,
    )
    confirmed = apply_intents(plan, (ConfirmPurchasePrice(identity(1002)),), metadata())
    assert confirmed.evaluation.gameweeks[0].sales[0].basis_confirmation == "user_confirmed"
    assert confirmed.evaluation.gameweeks[0].sales[0].purchase_price_tenths == 50
    corrected = apply_intents(plan, (CorrectPurchasePrice(identity(1002), 48),), metadata())
    sale = corrected.evaluation.gameweeks[0].sales[0]
    assert (sale.purchase_price_tenths, sale.selling_price_tenths) == (48, 51)
    assert sale.basis_confirmation == "user_confirmed"
