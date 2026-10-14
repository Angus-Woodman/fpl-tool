from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from fpl_engine.planning.models import (
    DecisionSale,
    Diagnostic,
    EvaluatedGameweek,
    GameweekDecision,
    LineupRole,
    Ownership,
    Plan,
    PlanEvaluation,
    PlayerRuleData,
    PurchaseProvenance,
)
from fpl_engine.planning.prices import selling_price_tenths
from fpl_engine.rules import (
    Chip,
    RuleViolationError,
    SquadSlot,
    free_transfers_after,
    has_unlimited_transfers,
    points_hit,
    validate_squad,
)
from fpl_engine.rules.chips import chip_states, validate_starting_declarations

EVALUATOR_VERSION = "planner-foundations-1"


def squad_slots(
    players: tuple[Ownership, ...],
    lineup: tuple[LineupRole, ...],
    metadata: Mapping[int, PlayerRuleData],
) -> tuple[SquadSlot, ...]:
    roles = {role.slot_id: role for role in lineup}
    slots: list[SquadSlot] = []
    for player in players:
        rule = metadata.get(player.player_id)
        if rule is None:
            raise RuleViolationError("missing_player", f"Unknown player {player.player_id}")
        role = roles[player.slot_id]
        slots.append(
            SquadSlot(
                player.player_id,
                rule.position,
                rule.team_id,
                role.is_starting,
                role.bench_order,
                role.is_captain,
                role.is_vice_captain,
            )
        )
    return tuple(slots)


def _apply_transfers(
    players: tuple[Ownership, ...],
    week: GameweekDecision,
) -> tuple[
    tuple[Ownership, ...], tuple[DecisionSale, ...], frozenset[UUID], tuple[Diagnostic, ...]
]:
    entering = {player.player_id: player for player in players}
    replacements: dict[int, Ownership] = {}
    sales: list[DecisionSale] = []
    dependencies: set[UUID] = set()
    errors: list[Diagnostic] = []
    for transfer in sorted(week.transfers, key=lambda decision: str(decision.decision_id)):
        outgoing = entering.get(transfer.outgoing_player_id)
        if outgoing is None or outgoing.ownership_id != transfer.outgoing_ownership_id:
            errors.append(
                Diagnostic(
                    "outgoing_not_owned",
                    f"Gameweek {week.gameweek_number}: intended outgoing player "
                    f"{transfer.outgoing_player_id} is not owned in that episode",
                    week.gameweek_number,
                    transfer.decision_id,
                    player_id=transfer.outgoing_player_id,
                )
            )
            continue
        if transfer.incoming_player_id in entering:
            errors.append(
                Diagnostic(
                    "incoming_already_owned",
                    "Incoming player is already owned",
                    week.gameweek_number,
                    transfer.decision_id,
                    player_id=transfer.incoming_player_id,
                )
            )
            continue
        sale = selling_price_tenths(outgoing.purchase_price_tenths, transfer.outgoing_market_tenths)
        sales.append(DecisionSale(transfer.decision_id, sale))
        if outgoing.provenance.confirmation == "assumed":
            dependencies.add(outgoing.ownership_id)
        replacements[outgoing.player_id] = Ownership(
            outgoing.slot_id,
            transfer.incoming_ownership_id,
            transfer.incoming_player_id,
            transfer.incoming_price_tenths,
            PurchaseProvenance(
                f"decision:{transfer.decision_id}@{transfer.observation_source}"
                f"@{transfer.observed_at}",
                transfer.incoming_price_tenths,
                "planned_acquisition",
                None,
            ),
        )
    return (
        tuple(replacements.get(player.player_id, player) for player in players),
        tuple(sales),
        frozenset(dependencies),
        tuple(errors),
    )


def resolve_lineup_membership(plan: Plan, gameweek_number: int) -> tuple[Ownership, ...] | None:
    permanent = plan.boundary.players
    for week in plan.gameweeks:
        players, _, _, errors = _apply_transfers(permanent, week)
        if errors:
            return None
        if week.gameweek_number == gameweek_number:
            return players
        if week.chip != Chip.FREE_HIT:
            permanent = players
    return None


def evaluate_plan(plan: Plan, metadata: Mapping[int, PlayerRuleData]) -> PlanEvaluation:
    permanent_players: tuple[Ownership, ...] | None = plan.boundary.players
    permanent_bank: int | None = plan.boundary.bank_tenths
    available = plan.boundary.free_transfers
    bank_dependencies = plan.boundary.bank_assumptions
    permanent_issues: frozenset[int] = frozenset()
    results: list[EvaluatedGameweek] = []
    diagnostics: list[Diagnostic] = []
    try:
        validate_starting_declarations(
            plan.start_gameweek, plan.boundary.used_chips, plan.boundary.free_hit_gameweek_19
        )
        if (plan.start_gameweek == 1) != (plan.boundary.free_transfers is None):
            raise RuleViolationError("starting_transfers", "Starting FT is N/A only at gameweek 1")
    except RuleViolationError as error:
        diagnostics.append(Diagnostic(error.code, str(error), plan.start_gameweek))
    planned_chips = {week.gameweek_number: week.chip for week in plan.gameweeks}
    for week in plan.gameweeks:
        if week.chip is not None:
            state = chip_states(
                week.gameweek_number,
                planned_chips,
                start_gameweek=plan.start_gameweek,
                used_chips=plan.boundary.used_chips,
                free_hit_gameweek_19=plan.boundary.free_hit_gameweek_19,
            )[week.chip]
            if state.state not in {"available", "planned_here"}:
                diagnostics.append(
                    Diagnostic(
                        f"chip_{state.state}",
                        state.reason or "Chip unavailable",
                        week.gameweek_number,
                        conflicting_gameweek=state.conflicting_gameweek,
                    )
                )
        unlimited = has_unlimited_transfers(gameweek_number=week.gameweek_number, chip=week.chip)
        starting_bank = permanent_bank
        players: tuple[Ownership, ...] | None = None
        sales: tuple[DecisionSale, ...] = ()
        dependencies = bank_dependencies
        errors: tuple[Diagnostic, ...] = ()
        if permanent_players is None:
            errors = (
                Diagnostic(
                    "dependency_blocked",
                    "Entering ownership/accounting is unavailable",
                    week.gameweek_number,
                ),
            )
        else:
            candidate, sales, sale_dependencies, errors = _apply_transfers(permanent_players, week)
            dependencies |= sale_dependencies
            if not errors:
                try:
                    validate_squad(squad_slots(candidate, week.lineup, metadata))
                except RuleViolationError as error:
                    errors = (Diagnostic(error.code, str(error), week.gameweek_number),)
            if not errors:
                players = candidate
        diagnostics.extend(errors)
        count = None if errors else len(week.transfers)
        bank: int | None = None
        hit: int | None = None
        next_ft: int | None = None
        issues = permanent_issues
        if not errors and starting_bank is not None:
            bank = (
                starting_bank
                + sum(sale.selling_price_tenths for sale in sales)
                - sum(transfer.incoming_price_tenths for transfer in week.transfers)
            )
            if bank < 0:
                issues |= {week.gameweek_number}
        if count is not None and (available is not None or week.gameweek_number == 1):
            hit = points_hit(
                transfers_made=count,
                free_transfers_available=available or 0,
                chip=week.chip,
                gameweek_number=week.gameweek_number,
            )
            next_ft = free_transfers_after(
                available=available or 0,
                transfers_made=count,
                chip=week.chip,
                gameweek_number=week.gameweek_number,
            )
        elif unlimited and (available is not None or week.gameweek_number == 1):
            next_ft = free_transfers_after(
                available=available or 0,
                transfers_made=0,
                chip=week.chip,
                gameweek_number=week.gameweek_number,
            )
        if week.chip != Chip.FREE_HIT:
            permanent_players, permanent_bank = players, bank
            bank_dependencies, permanent_issues = dependencies, issues
        if players is not None:
            dependencies |= frozenset(
                player.ownership_id
                for player in players
                if player.provenance.confirmation == "assumed"
            )
        results.append(
            EvaluatedGameweek(
                week.gameweek_number,
                players,
                week.lineup,
                starting_bank,
                bank,
                available,
                next_ft,
                unlimited,
                count,
                hit,
                permanent_players,
                permanent_bank,
                dependencies,
                issues,
                sales,
                bank_dependencies,
            )
        )
        available = next_ft
    return PlanEvaluation(tuple(results), tuple(diagnostics))
