from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from fpl_engine.planning.evaluate import evaluate_plan, resolve_lineup_membership, squad_slots
from fpl_engine.planning.models import (
    AddTransfer,
    ChangeCaptain,
    ChangeHorizon,
    ChangeViceCaptain,
    ConfirmPurchasePrice,
    CorrectPurchasePrice,
    Diagnostic,
    EditTransfer,
    GameweekDecision,
    Intent,
    MoveChip,
    Plan,
    PlanEvaluation,
    PlayerRuleData,
    RemoveTransfer,
    RenamePlan,
    SetChip,
    SetStartingChips,
    SetStartingTransfers,
    SwapLineupPlayers,
)
from fpl_engine.rules import Chip, RuleViolationError, season_half, validate_squad


class MutationRejectedError(RuleViolationError):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        first = diagnostics[0]
        super().__init__(first.code, f"Gameweek {first.gameweek_number}: {first.message}")


@dataclass(frozen=True)
class MutationResult:
    plan: Plan
    evaluation: PlanEvaluation


def _diagnostic_key(error: Diagnostic) -> tuple[object, ...]:
    return (
        error.code,
        error.gameweek_number,
        error.decision_id,
        error.conflicting_gameweek,
        error.player_id,
    )


def validate_candidate(
    previous: Plan,
    candidate: Plan,
    metadata: Mapping[int, PlayerRuleData],
    *,
    purchase_correction: bool = False,
) -> PlanEvaluation:
    before = evaluate_plan(previous, metadata)
    after = evaluate_plan(candidate, metadata)
    existing = {_diagnostic_key(error) for error in before.diagnostics}
    introduced = tuple(
        error for error in after.diagnostics if _diagnostic_key(error) not in existing
    )
    if introduced:
        previous_chips = {week.gameweek_number: week.chip for week in previous.gameweeks}
        changed_chips = {
            week.gameweek_number
            for week in candidate.gameweeks
            if week.chip is not None and week.chip != previous_chips.get(week.gameweek_number)
        }
        introduced = tuple(
            sorted(
                introduced,
                key=lambda error: not (
                    error.code.startswith("chip_") and error.gameweek_number in changed_chips
                ),
            )
        )
        raise MutationRejectedError(introduced)
    if not purchase_correction:
        old_weeks = {week.gameweek_number: week for week in before.gameweeks}
        for week in after.gameweeks:
            old = old_weeks.get(week.gameweek_number)
            current_shortfall = week.shortfall_tenths
            prior_shortfall = old.shortfall_tenths if old is not None else 0
            if current_shortfall is None:
                continue
            worsened = (
                current_shortfall > 0
                if prior_shortfall is None
                else current_shortfall > prior_shortfall
            )
            if worsened:
                raise MutationRejectedError(
                    (
                        Diagnostic(
                            "financial_shortfall",
                            f"New or worsened shortfall of {current_shortfall} tenths",
                            week.gameweek_number,
                        ),
                    )
                )
    return after


def _transfer_changes(plan: Plan, intents: tuple[Intent, ...]) -> Plan:
    transfers = {
        week.gameweek_number: {decision.decision_id: decision for decision in week.transfers}
        for week in plan.gameweeks
    }
    for intent in intents:
        if isinstance(intent, AddTransfer):
            if intent.gameweek_number not in transfers:
                raise RuleViolationError("gameweek_not_in_plan", "Transfer GW is outside the plan")
            if any(intent.decision.decision_id in decisions for decisions in transfers.values()):
                raise RuleViolationError("duplicate_transfer", "Decision already exists")
            transfers[intent.gameweek_number][intent.decision.decision_id] = intent.decision
        elif isinstance(intent, EditTransfer | RemoveTransfer):
            number = next(
                (
                    number
                    for number, decisions in transfers.items()
                    if intent.decision_id in decisions
                ),
                None,
            )
            if number is None:
                raise RuleViolationError("decision_not_found", "Transfer decision no longer exists")
            if isinstance(intent, EditTransfer):
                if intent.decision.decision_id != intent.decision_id:
                    raise RuleViolationError(
                        "decision_identity", "Editing preserves the decision ID"
                    )
                previous = transfers[number][intent.decision_id]
                if (
                    previous.incoming_player_id == intent.decision.incoming_player_id
                    and previous.incoming_ownership_id != intent.decision.incoming_ownership_id
                ):
                    raise RuleViolationError(
                        "ownership_identity", "Unchanged acquisition keeps its ID"
                    )
                transfers[number][intent.decision_id] = intent.decision
            else:
                del transfers[number][intent.decision_id]
    return replace(
        plan,
        gameweeks=tuple(
            replace(
                week,
                transfers=tuple(
                    sorted(
                        transfers[week.gameweek_number].values(),
                        key=lambda transfer: str(transfer.decision_id),
                    )
                ),
            )
            for week in plan.gameweeks
        ),
    )


def _change_horizon(
    plan: Plan, intent: ChangeHorizon, metadata: Mapping[int, PlayerRuleData]
) -> Plan:
    season_half(intent.start_gameweek)
    season_half(intent.end_gameweek)
    if intent.start_gameweek > intent.end_gameweek:
        raise RuleViolationError("plan_horizon", "Start gameweek must not exceed end gameweek")
    boundary = plan.boundary
    if intent.start_gameweek > plan.start_gameweek:
        prefix_end = intent.start_gameweek - 1
        extended_end = max(plan.end_gameweek, prefix_end)
        weeks = {week.gameweek_number: week for week in plan.gameweeks}
        expanded = replace(
            plan,
            end_gameweek=extended_end,
            gameweeks=tuple(
                weeks.get(number, GameweekDecision(number, boundary.lineup))
                for number in range(plan.start_gameweek, extended_end + 1)
            ),
        )
        evaluation = evaluate_plan(expanded, metadata)
        errors = tuple(
            error for error in evaluation.diagnostics if error.gameweek_number <= prefix_end
        )
        prefix = tuple(week for week in evaluation.gameweeks if week.gameweek_number <= prefix_end)
        if errors or any(week.financial_issue_gameweeks for week in prefix):
            raise RuleViolationError("unresolved_prefix", "Cannot rebase an unresolved plan prefix")
        last = prefix[-1]
        if last.permanent_players is None or last.permanent_bank_tenths is None:
            raise RuleViolationError("unresolved_prefix", "Permanent prefix exit is unavailable")
        used = (
            set(boundary.used_chips)
            if (season_half(plan.start_gameweek) == season_half(intent.start_gameweek))
            else set()
        )
        used.update(
            week.chip
            for week in expanded.gameweeks
            if week.gameweek_number <= prefix_end
            and week.chip is not None
            and season_half(week.gameweek_number) == season_half(intent.start_gameweek)
        )
        fh19 = intent.start_gameweek == 20 and any(
            week.gameweek_number == 19 and week.chip == Chip.FREE_HIT for week in expanded.gameweeks
        )
        boundary = replace(
            boundary,
            players=last.permanent_players,
            bank_tenths=last.permanent_bank_tenths,
            free_transfers=last.next_free_transfers,
            used_chips=frozenset(used),
            free_hit_gameweek_19=fh19,
            origin="rebased_plan",
            bank_assumptions=last.permanent_bank_dependencies,
        )
    elif intent.start_gameweek < plan.start_gameweek:
        boundary = replace(
            boundary,
            origin="earlier_horizon_assumed",
            used_chips=(
                boundary.used_chips
                if season_half(plan.start_gameweek) == season_half(intent.start_gameweek)
                and intent.start_gameweek not in (1, 20)
                else frozenset()
            ),
            free_hit_gameweek_19=False,
            free_transfers=(
                None
                if intent.start_gameweek == 1
                else 1
                if boundary.free_transfers is None
                else boundary.free_transfers
            ),
        )
    if intent.used_chips is not None:
        boundary = replace(boundary, used_chips=intent.used_chips)
    if intent.free_hit_gameweek_19 is not None:
        boundary = replace(boundary, free_hit_gameweek_19=intent.free_hit_gameweek_19)
    retained = {week.gameweek_number: week for week in plan.gameweeks}
    return replace(
        plan,
        start_gameweek=intent.start_gameweek,
        end_gameweek=intent.end_gameweek,
        boundary=boundary,
        gameweeks=tuple(
            retained.get(number, GameweekDecision(number, boundary.lineup))
            for number in range(intent.start_gameweek, intent.end_gameweek + 1)
        ),
    )


def _lineup_change(
    plan: Plan,
    intent: ChangeCaptain | ChangeViceCaptain | SwapLineupPlayers,
    metadata: Mapping[int, PlayerRuleData],
) -> Plan:
    evaluation = evaluate_plan(plan, metadata)
    evaluated = next(
        (week for week in evaluation.gameweeks if week.gameweek_number == intent.gameweek_number),
        None,
    )
    if evaluated is None:
        raise RuleViolationError("lineup_unavailable", "Cannot edit an unavailable lineup")
    owned = evaluated.players
    if owned is None and any(
        error.gameweek_number == intent.gameweek_number and error.code != "dependency_blocked"
        for error in evaluation.diagnostics
    ):
        owned = resolve_lineup_membership(plan, intent.gameweek_number)
    if owned is None:
        raise RuleViolationError("lineup_unavailable", "Cannot edit an unavailable lineup")
    players = {player.player_id: player for player in owned}
    roles = {role.slot_id: role for role in evaluated.lineup}
    if isinstance(intent, ChangeCaptain | ChangeViceCaptain):
        if intent.player_id not in players:
            raise RuleViolationError("player_not_owned", "Selected player is no longer owned")
        selected = players[intent.player_id].slot_id
        lineup = tuple(
            replace(role, is_captain=role.slot_id == selected)
            if isinstance(intent, ChangeCaptain)
            else replace(role, is_vice_captain=role.slot_id == selected)
            for role in evaluated.lineup
        )
    else:
        first = players.get(intent.first_player_id)
        second = players.get(intent.second_player_id)
        if first is None or second is None or first == second:
            raise RuleViolationError("invalid_swap", "Select two distinct owned players")
        first_role, second_role = roles[first.slot_id], roles[second.slot_id]
        if first_role.is_starting and second_role.is_starting:
            raise RuleViolationError(
                "invalid_swap", "Select a starter and bench player or two outfield substitutes"
            )
        if (
            not first_role.is_starting
            and not second_role.is_starting
            and (
                metadata[first.player_id].position.value == "GK"
                or metadata[second.player_id].position.value == "GK"
            )
        ):
            raise RuleViolationError(
                "invalid_swap", "Goalkeeper cannot reorder with outfield bench"
            )
        replacements = {
            first.slot_id: replace(second_role, slot_id=first.slot_id),
            second.slot_id: replace(first_role, slot_id=second.slot_id),
        }
        lineup = tuple(replacements.get(role.slot_id, role) for role in evaluated.lineup)
    validate_squad(squad_slots(owned, lineup, metadata))
    return replace(
        plan,
        gameweeks=tuple(
            replace(week, lineup=lineup) if week.gameweek_number == intent.gameweek_number else week
            for week in plan.gameweeks
        ),
    )


def legal_rearrangements(
    plan: Plan, gameweek_number: int, metadata: Mapping[int, PlayerRuleData]
) -> tuple[dict[str, int | str], ...]:
    evaluated = next(
        (
            week
            for week in evaluate_plan(plan, metadata).gameweeks
            if week.gameweek_number == gameweek_number
        ),
        None,
    )
    if evaluated is None or evaluated.players is None:
        return ()
    roles = {role.slot_id: role for role in evaluated.lineup}
    output: list[dict[str, int | str]] = []
    for first_index, first in enumerate(evaluated.players):
        for second in evaluated.players[first_index + 1 :]:
            first_role, second_role = roles[first.slot_id], roles[second.slot_id]
            if first_role.is_starting and second_role.is_starting:
                continue
            if (
                not first_role.is_starting
                and not second_role.is_starting
                and (
                    metadata[first.player_id].position.value == "GK"
                    or metadata[second.player_id].position.value == "GK"
                )
            ):
                continue
            replacements = {
                first.slot_id: replace(second_role, slot_id=first.slot_id),
                second.slot_id: replace(first_role, slot_id=second.slot_id),
            }
            lineup = tuple(replacements.get(role.slot_id, role) for role in evaluated.lineup)
            try:
                validate_squad(squad_slots(evaluated.players, lineup, metadata))
            except RuleViolationError:
                continue
            output.append(
                {
                    "first_player_id": first.player_id,
                    "second_player_id": second.player_id,
                    "kind": "substitution"
                    if first_role.is_starting != second_role.is_starting
                    else "bench_priority",
                }
            )
    return tuple(output)


def apply_intents(
    plan: Plan, intents: tuple[Intent, ...], metadata: Mapping[int, PlayerRuleData]
) -> MutationResult:
    if not intents:
        raise RuleViolationError("empty_mutation", "At least one intent is required")
    corrections = tuple(
        isinstance(intent, CorrectPurchasePrice | ConfirmPurchasePrice) for intent in intents
    )
    if any(corrections) and not all(corrections):
        raise RuleViolationError(
            "mixed_purchase_correction", "Cannot mix corrections with planning edits"
        )
    candidate = _transfer_changes(plan, intents)
    chips = {week.gameweek_number: week.chip for week in candidate.gameweeks}
    for intent in intents:
        if isinstance(intent, RenamePlan):
            if not intent.name.strip():
                raise RuleViolationError("plan_name", "Plan name cannot be empty")
            candidate = replace(candidate, name=intent.name.strip())
        elif isinstance(intent, SetStartingTransfers):
            candidate = replace(
                candidate, boundary=replace(candidate.boundary, free_transfers=intent.value)
            )
        elif isinstance(intent, SetStartingChips):
            candidate = replace(
                candidate,
                boundary=replace(
                    candidate.boundary,
                    used_chips=intent.used_chips,
                    free_hit_gameweek_19=intent.free_hit_gameweek_19,
                ),
            )
        elif isinstance(intent, CorrectPurchasePrice | ConfirmPurchasePrice):
            if not any(
                player.ownership_id == intent.ownership_id for player in candidate.boundary.players
            ):
                raise RuleViolationError(
                    "ownership_not_found", "Starting ownership no longer exists"
                )
            updated = []
            for player in candidate.boundary.players:
                if player.ownership_id == intent.ownership_id:
                    provenance = player.provenance
                    if provenance.basis_kind == "starting":
                        provenance = replace(provenance, confirmation="user_confirmed")
                    player = replace(
                        player,
                        provenance=provenance,
                        purchase_price_tenths=intent.price_tenths
                        if isinstance(intent, CorrectPurchasePrice)
                        else player.purchase_price_tenths,
                    )
                updated.append(player)
            candidate = replace(
                candidate, boundary=replace(candidate.boundary, players=tuple(updated))
            )
        elif isinstance(intent, SetChip):
            if intent.gameweek_number not in chips:
                raise RuleViolationError("gameweek_not_in_plan", "Chip GW is outside the plan")
            current = chips[intent.gameweek_number]
            if current != intent.expected_chip or (current is not None and intent.chip is not None):
                raise RuleViolationError(
                    "chip_conflict", "Remove the existing chip explicitly first"
                )
            chips[intent.gameweek_number] = intent.chip
        elif isinstance(intent, MoveChip):
            if (
                intent.source_gameweek not in chips
                or intent.target_gameweek not in chips
                or chips[intent.source_gameweek] != intent.chip
                or chips[intent.target_gameweek] is not None
            ):
                raise RuleViolationError("chip_conflict", "Chip move source/target has changed")
            chips[intent.source_gameweek], chips[intent.target_gameweek] = None, intent.chip
    candidate = replace(
        candidate,
        gameweeks=tuple(
            replace(week, chip=chips[week.gameweek_number]) for week in candidate.gameweeks
        ),
    )
    for intent in intents:
        if isinstance(intent, ChangeHorizon):
            candidate = _change_horizon(candidate, intent, metadata)
        elif isinstance(intent, ChangeCaptain | ChangeViceCaptain | SwapLineupPlayers):
            candidate = _lineup_change(candidate, intent, metadata)
    evaluation = validate_candidate(plan, candidate, metadata, purchase_correction=all(corrections))
    for intent in intents:
        if isinstance(intent, AddTransfer | EditTransfer):
            decision_id = intent.decision.decision_id
            target = next(
                week.gameweek_number
                for week in candidate.gameweeks
                if any(decision.decision_id == decision_id for decision in week.transfers)
            )
            result = next(week for week in evaluation.gameweeks if week.gameweek_number == target)
            if result.closing_bank_tenths is None:
                raise RuleViolationError(
                    "unverified_edit", "Cannot verify an edit beyond a blocked dependency"
                )
    return MutationResult(candidate, evaluation)
