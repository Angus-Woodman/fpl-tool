from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.evaluate import EVALUATOR_VERSION, evaluate_plan
from fpl_engine.planning.models import PlayerRuleData
from fpl_engine.planning.mutations import legal_rearrangements
from fpl_engine.rules import Chip, SquadSlot, has_unlimited_transfers, score_gameweek
from fpl_engine.rules.chips import chip_states

from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.plan_repository import PlanGameweekRecord, PlanPlayerRecord, PlanRecord
from api.services.plans import checked_tenths


@dataclass(frozen=True)
class PlanFixtureViewRecord:
    fixture_id: int | None
    projected_points: float
    kickoff_time: str
    opponent_team_short_name: str | None
    is_home: bool | None


@dataclass(frozen=True)
class PlanPlayerViewRecord:
    player_id: int
    web_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool
    projected_points: float
    fixtures: list[PlanFixtureViewRecord]
    slot_id: str | None = None
    ownership_id: str | None = None
    source_decision_id: str | None = None
    purchase_price_tenths: int | None = None
    provenance: dict[str, object] | None = None


@dataclass(frozen=True)
class PlanTransferViewRecord:
    player_id: int
    web_name: str


@dataclass(frozen=True)
class PlanGameweekViewRecord:
    gameweek_number: int
    chip: str | None
    bank: float | None
    free_transfers_available: int | None
    unlimited_transfers: bool
    transfers_made: int | None
    points_hit: int | None
    starting_points: float | None
    bench_points: float | None
    captain_bonus_points: float | None
    total_points: float | None
    players: list[PlanPlayerViewRecord]
    transfers_in: list[PlanTransferViewRecord]
    transfers_out: list[PlanTransferViewRecord]
    decisions: list[dict[str, object]] = field(default_factory=list)
    accounting: dict[str, object] | None = None
    chip_availability: dict[str, object] = field(default_factory=dict)
    evaluation_status: str = "complete"
    legal_rearrangements: tuple[dict[str, int | str], ...] = ()


@dataclass(frozen=True)
class PlanViewRecord:
    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int
    initial_bank: float
    initial_free_transfers: int
    total_points: float | None
    total_points_hit: int | None
    gameweeks: list[PlanGameweekViewRecord]
    revision: int = 0
    evaluator_version: str = EVALUATOR_VERSION
    foundation_state: str = "legacy_pending"
    starting_state: dict[str, object] | None = None
    financial_status: dict[str, object] = field(default_factory=dict)
    decision_errors: list[dict[str, object]] = field(default_factory=list)
    initialization: dict[str, object] = field(default_factory=dict)


def _live_tenths(lookup: dict[int, PlanPlayerRecord], player_id: int) -> int | None:
    # Display only: latest market is never a financial input to replay.
    player = lookup.get(player_id)
    if player is None:
        return None
    try:
        return checked_tenths(player.current_price)
    except ValueError:
        return None


class PlanProjectionRepositoryPort(Protocol):
    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]: ...


class GetPlanViewService:
    def __init__(self, projection_repository: PlanProjectionRepositoryPort) -> None:
        self._projection_repository = projection_repository

    def execute(self, plan: PlanRecord) -> PlanViewRecord:
        if plan.canonical_plan is not None:
            return self._canonical_view(plan)
        player_ids = sorted(
            {player.player_id for gameweek in plan.gameweeks for player in gameweek.players}
        )
        rows = self._projection_repository.list_latest_player_fixture_projections(player_ids)

        points_by_player_gameweek: dict[tuple[int, int], float] = defaultdict(float)
        fixtures_by_player_gameweek: dict[tuple[int, int], list[PlanFixtureViewRecord]] = (
            defaultdict(list)
        )
        for row in rows:
            key = (row.player_id, row.gameweek_number)
            points_by_player_gameweek[key] += row.projected_points
            fixtures_by_player_gameweek[key].append(
                PlanFixtureViewRecord(
                    fixture_id=row.fixture_id,
                    projected_points=row.projected_points,
                    kickoff_time=row.kickoff_time,
                    opponent_team_short_name=row.opponent_team_short_name,
                    is_home=row.is_home,
                )
            )

        names_by_player = {
            player.player_id: player.web_name
            for gameweek in plan.gameweeks
            for player in gameweek.players
        }

        gameweeks: list[PlanGameweekViewRecord] = []
        for gameweek in plan.gameweeks:
            chip = Chip(gameweek.chip) if gameweek.chip is not None else None
            projected_points = {
                player.player_id: points_by_player_gameweek.get(
                    (player.player_id, gameweek.gameweek_number), 0.0
                )
                for player in gameweek.players
            }
            score = score_gameweek(
                slots=[
                    SquadSlot(
                        player_id=player.player_id,
                        position=PlayerPosition(player.position),
                        team_id=player.team_id,
                        is_starting=player.is_starting,
                        bench_order=player.bench_order,
                        is_captain=player.is_captain,
                        is_vice_captain=player.is_vice_captain,
                    )
                    for player in gameweek.players
                ],
                projected_points=projected_points,
                chip=chip,
                points_hit=gameweek.points_hit or 0,
            )

            incoming: list[int] = []
            outgoing: list[int] = []

            gameweeks.append(
                PlanGameweekViewRecord(
                    gameweek_number=gameweek.gameweek_number,
                    chip=gameweek.chip,
                    bank=gameweek.bank,
                    free_transfers_available=gameweek.free_transfers_available,
                    unlimited_transfers=has_unlimited_transfers(
                        gameweek_number=gameweek.gameweek_number, chip=chip
                    ),
                    transfers_made=gameweek.transfers_made,
                    points_hit=gameweek.points_hit,
                    starting_points=round(score.starting_points, 2),
                    bench_points=round(score.bench_points, 2),
                    captain_bonus_points=round(score.captain_bonus_points, 2),
                    total_points=round(score.total_points, 2),
                    players=[
                        PlanPlayerViewRecord(
                            player_id=player.player_id,
                            web_name=player.web_name,
                            team_short_name=player.team_short_name,
                            position=player.position,
                            current_price=player.current_price,
                            status=player.status,
                            is_starting=player.is_starting,
                            bench_order=player.bench_order,
                            is_captain=player.is_captain,
                            is_vice_captain=player.is_vice_captain,
                            projected_points=round(projected_points[player.player_id], 2),
                            fixtures=fixtures_by_player_gameweek.get(
                                (player.player_id, gameweek.gameweek_number), []
                            ),
                        )
                        for player in gameweek.players
                    ],
                    transfers_in=[
                        PlanTransferViewRecord(
                            player_id=player_id,
                            web_name=names_by_player.get(player_id, ""),
                        )
                        for player_id in incoming
                    ],
                    transfers_out=[
                        PlanTransferViewRecord(
                            player_id=player_id,
                            web_name=names_by_player.get(player_id, ""),
                        )
                        for player_id in outgoing
                    ],
                )
            )

        return PlanViewRecord(
            plan_id=plan.plan_id,
            name=plan.name,
            start_gameweek=plan.start_gameweek,
            end_gameweek=plan.end_gameweek,
            initial_bank=plan.initial_bank,
            initial_free_transfers=plan.initial_free_transfers,
            total_points=round(sum(item.total_points or 0 for item in gameweeks), 2),
            total_points_hit=sum(item.points_hit or 0 for item in gameweeks),
            gameweeks=gameweeks,
            initialization={
                "ready": False,
                "reason": plan.initialization_reason or "Explicit initialization required",
                "retryable": True,
            },
        )

    def _canonical_view(self, record: PlanRecord) -> PlanViewRecord:
        plan = record.canonical_plan
        assert plan is not None
        lookup = {player.player_id: player for player in record.rule_players}
        metadata = {
            identifier: PlayerRuleData(identifier, PlayerPosition(player.position), player.team_id)
            for identifier, player in lookup.items()
        }
        evaluation = evaluate_plan(plan, metadata)
        earliest = next((week for week in evaluation.gameweeks if week.shortfall_tenths), None)
        weeks: list[PlanGameweekRecord] = []
        for week, evaluated in zip(plan.gameweeks, evaluation.gameweeks, strict=True):
            roles = {role.slot_id: role for role in week.lineup}
            players = []
            for player in evaluated.players or ():
                role = roles[player.slot_id]
                players.append(
                    replace(
                        lookup[player.player_id],
                        is_starting=role.is_starting,
                        bench_order=role.bench_order,
                        is_captain=role.is_captain,
                        is_vice_captain=role.is_vice_captain,
                    )
                )
            weeks.append(
                PlanGameweekRecord(
                    week.gameweek_number,
                    week.chip.value if week.chip else None,
                    evaluated.closing_bank_tenths / 10
                    if evaluated.closing_bank_tenths is not None
                    else None,
                    evaluated.free_transfers_available,
                    evaluated.transfers_made,
                    evaluated.points_hit,
                    players,
                )
            )
        enriched = self.execute(replace(record, canonical_plan=None, gameweeks=weeks))
        chips = {week.gameweek_number: week.chip for week in plan.gameweeks}
        acquisition_ids = {
            decision.incoming_ownership_id: str(decision.decision_id)
            for week in plan.gameweeks
            for decision in week.transfers
        }
        output = []
        for week, evaluated, view in zip(
            plan.gameweeks, evaluation.gameweeks, enriched.gameweeks, strict=True
        ):
            ownership = {player.player_id: player for player in evaluated.players or ()}
            sales = {sale.decision_id: sale for sale in evaluated.sales}
            output.append(
                replace(
                    view,
                    players=[
                        replace(
                            player,
                            slot_id=str(ownership[player.player_id].slot_id),
                            ownership_id=str(ownership[player.player_id].ownership_id),
                            source_decision_id=acquisition_ids.get(
                                ownership[player.player_id].ownership_id
                            ),
                            purchase_price_tenths=ownership[player.player_id].purchase_price_tenths,
                            provenance=asdict(ownership[player.player_id].provenance),
                        )
                        for player in view.players
                    ],
                    decisions=[
                        {
                            **asdict(decision),
                            "selling_price_tenths": sale.selling_price_tenths if sale else None,
                            "purchase_price_tenths": sale.purchase_price_tenths if sale else None,
                            "basis_kind": sale.basis_kind if sale else None,
                            "basis_confirmation": sale.basis_confirmation if sale else None,
                            "outgoing_live_market_tenths": _live_tenths(
                                lookup, decision.outgoing_player_id
                            ),
                            "incoming_live_price_tenths": _live_tenths(
                                lookup, decision.incoming_player_id
                            ),
                        }
                        for decision in week.transfers
                        for sale in (sales.get(decision.decision_id),)
                    ],
                    transfers_in=[
                        PlanTransferViewRecord(
                            decision.incoming_player_id,
                            lookup[decision.incoming_player_id].web_name
                            if decision.incoming_player_id in lookup
                            else "Unknown",
                        )
                        for decision in week.transfers
                    ],
                    transfers_out=[
                        PlanTransferViewRecord(
                            decision.outgoing_player_id,
                            lookup[decision.outgoing_player_id].web_name
                            if decision.outgoing_player_id in lookup
                            else "Unknown",
                        )
                        for decision in week.transfers
                    ],
                    accounting={
                        "starting_bank_tenths": evaluated.starting_bank_tenths,
                        "closing_bank_tenths": evaluated.closing_bank_tenths,
                        "free_transfers_available": evaluated.free_transfers_available,
                        "next_free_transfers": evaluated.next_free_transfers,
                        "unlimited_transfers": evaluated.unlimited_transfers,
                        "transfers_made": evaluated.transfers_made,
                        "points_hit": evaluated.points_hit,
                    },
                    chip_availability={
                        chip.value: asdict(state)
                        for chip, state in chip_states(
                            week.gameweek_number,
                            chips,
                            start_gameweek=plan.start_gameweek,
                            used_chips=plan.boundary.used_chips,
                            free_hit_gameweek_19=plan.boundary.free_hit_gameweek_19,
                        ).items()
                    },
                    evaluation_status="blocked" if evaluated.players is None else "complete",
                    starting_points=view.starting_points if evaluated.players is not None else None,
                    bench_points=view.bench_points if evaluated.players is not None else None,
                    captain_bonus_points=view.captain_bonus_points
                    if evaluated.players is not None
                    else None,
                    total_points=view.total_points if evaluated.players is not None else None,
                    legal_rearrangements=legal_rearrangements(plan, week.gameweek_number, metadata),
                )
            )
        starting = asdict(plan.boundary)
        starting["players"] = [
            {
                **asdict(player),
                "web_name": lookup[player.player_id].web_name
                if player.player_id in lookup
                else "Unknown",
            }
            for player in plan.boundary.players
        ]
        return replace(
            enriched,
            name=plan.name,
            start_gameweek=plan.start_gameweek,
            end_gameweek=plan.end_gameweek,
            initial_bank=plan.boundary.bank_tenths / 10,
            initial_free_transfers=plan.boundary.free_transfers or 0,
            total_points=None
            if any(week.players is None for week in evaluation.gameweeks)
            else enriched.total_points,
            total_points_hit=None
            if any(week.points_hit is None for week in evaluation.gameweeks)
            else enriched.total_points_hit,
            gameweeks=output,
            revision=plan.revision,
            foundation_state="ready",
            starting_state=starting,
            decision_errors=[asdict(error) for error in evaluation.diagnostics],
            financial_status={
                "provisional": any(week.provisional_dependencies for week in evaluation.gameweeks),
                "earliest_shortfall_gameweek": evaluation.earliest_shortfall_gameweek,
                "earliest_shortfall_tenths": earliest.shortfall_tenths if earliest else None,
                "earliest_shortfall_reason": (
                    f"Bank is £{earliest.shortfall_tenths / 10:.1f}m below zero in gameweek "
                    f"{earliest.gameweek_number} after its saved transfers"
                    if earliest and earliest.shortfall_tenths
                    else None
                ),
                "requires_resolution": evaluation.earliest_shortfall_gameweek is not None,
                "gameweeks": [
                    {
                        "gameweek_number": week.gameweek_number,
                        "shortfall_tenths": week.shortfall_tenths,
                        "affected_chain": sorted(week.financial_issue_gameweeks),
                        "provisional": bool(week.provisional_dependencies),
                    }
                    for week in evaluation.gameweeks
                ],
            },
            initialization={"ready": True, "boundary_origin": plan.boundary.origin},
        )


__all__ = [
    "GetPlanViewService",
    "PlanFixtureViewRecord",
    "PlanGameweekViewRecord",
    "PlanPlayerViewRecord",
    "PlanTransferViewRecord",
    "PlanViewRecord",
]
