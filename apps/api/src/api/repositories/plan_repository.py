from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from fpl_engine.planning.models import (
    Boundary,
    BoundaryOrigin,
    GameweekDecision,
    LineupRole,
    Ownership,
    Plan,
    PlanEvaluation,
    PurchaseProvenance,
    TransferDecision,
)
from fpl_engine.rules import Chip
from pydantic import TypeAdapter
from sqlalchemy import delete, null, select, update
from sqlalchemy.orm import Session

from api.models import (
    PlanChip,
    PlanGameweekModel,
    PlanGameweekPlayerModel,
    PlanModel,
    PlayerModel,
    TeamModel,
)
from api.models.entities import (
    PlanMutationModel,
    PlanStartingPlayerModel,
    PlanTransferDecisionModel,
)

LINEUP_ADAPTER = TypeAdapter(tuple[LineupRole, ...])
PROVENANCE_ADAPTER = TypeAdapter(PurchaseProvenance)
TRANSFER_ADAPTER = TypeAdapter(TransferDecision)


class PlanNotReadyError(ValueError):
    def __init__(self, plan_id: int) -> None:
        super().__init__(f"Plan {plan_id} requires explicit Planner initialization")
        self.plan_id = plan_id


@dataclass(frozen=True)
class PlanPlayerRecord:
    player_id: int
    web_name: str
    first_name: str
    second_name: str
    team_id: int
    team_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


@dataclass(frozen=True)
class PlanGameweekRecord:
    gameweek_number: int
    chip: str | None
    bank: float | None
    free_transfers_available: int | None
    transfers_made: int | None
    points_hit: int | None
    players: list[PlanPlayerRecord]


@dataclass(frozen=True)
class PlanRecord:
    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int
    initial_bank: float
    initial_free_transfers: int
    gameweeks: list[PlanGameweekRecord]
    canonical_plan: Plan | None = None
    rule_players: list[PlanPlayerRecord] = field(default_factory=list)


@dataclass(frozen=True)
class PlanSummaryRecord:
    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int
    created_at: dt.datetime
    updated_at: dt.datetime


@dataclass(frozen=True)
class PlanPlayerSave:
    player_id: int
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


@dataclass(frozen=True)
class PlanGameweekAccounting:
    gameweek_number: int
    bank: float
    free_transfers_available: int
    transfers_made: int
    points_hit: int


class PlanNotFoundError(LookupError):
    def __init__(self, plan_id: int) -> None:
        super().__init__(f"Plan {plan_id} does not exist")
        self.plan_id = plan_id


class PlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_plan(self, plan_id: int, *, shared: bool = False) -> PlanModel:
        plan = self._session.scalar(
            select(PlanModel)
            .where(PlanModel.id == plan_id)
            .with_for_update(read=shared)
            .execution_options(populate_existing=True)
        )
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan

    def get_for_view(self, plan_id: int, *, canonical: Plan | None = None) -> PlanRecord | None:
        row = self._session.scalar(
            select(PlanModel)
            .where(PlanModel.id == plan_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        if row.foundation_state != "ready":
            return self.get(plan_id)
        plan = canonical if canonical is not None else self.load_canonical(plan_id)
        identifiers = {player.player_id for player in plan.boundary.players}
        for week in plan.gameweeks:
            for decision in week.transfers:
                identifiers.update((decision.outgoing_player_id, decision.incoming_player_id))
        rows = self._session.execute(
            select(PlayerModel, TeamModel)
            .join(TeamModel, TeamModel.id == PlayerModel.team_id)
            .where(PlayerModel.id.in_(identifiers))
        ).all()
        players = [
            PlanPlayerRecord(
                player.id,
                player.web_name,
                player.first_name,
                player.second_name,
                team.id,
                team.name,
                team.short_name,
                player.position.value,
                float(player.current_price),
                player.status,
                False,
                None,
                False,
                False,
            )
            for player, team in rows
        ]
        return PlanRecord(
            plan_id,
            plan.name,
            plan.start_gameweek,
            plan.end_gameweek,
            plan.boundary.bank_tenths / 10,
            plan.boundary.free_transfers or 0,
            [],
            plan,
            players,
        )

    def load_canonical(self, plan_id: int) -> Plan:
        row = self.lock_plan(plan_id, shared=True)
        if (
            row.foundation_state != "ready"
            or row.boundary_lineup is None
            or (row.initial_bank_tenths is None)
        ):
            raise PlanNotReadyError(plan_id)
        starting = self._session.scalars(
            select(PlanStartingPlayerModel)
            .where(PlanStartingPlayerModel.plan_id == plan_id)
            .order_by(PlanStartingPlayerModel.id)
            .execution_options(populate_existing=True)
        ).all()
        boundary = Boundary(
            tuple(
                Ownership(
                    player.slot_id,
                    player.ownership_id,
                    player.player_id,
                    player.purchase_price_tenths,
                    PROVENANCE_ADAPTER.validate_python(player.provenance),
                )
                for player in starting
            ),
            LINEUP_ADAPTER.validate_python(row.boundary_lineup),
            row.initial_bank_tenths,
            row.starting_free_transfers,
            frozenset(Chip(chip) for chip in row.used_chips),
            row.free_hit_gameweek_19,
            TypeAdapter(BoundaryOrigin).validate_python(row.boundary_origin),
            frozenset(UUID(value) for value in row.bank_assumptions),
        )
        weeks = self._session.scalars(
            select(PlanGameweekModel)
            .where(PlanGameweekModel.plan_id == plan_id)
            .order_by(PlanGameweekModel.gameweek_number)
            .execution_options(populate_existing=True)
        ).all()
        decisions = self._session.scalars(
            select(PlanTransferDecisionModel)
            .join(PlanGameweekModel)
            .where(PlanGameweekModel.plan_id == plan_id)
            .order_by(PlanTransferDecisionModel.decision_id)
            .execution_options(populate_existing=True)
        ).all()
        transfers: dict[int, list[TransferDecision]] = {}
        for decision in decisions:
            transfers.setdefault(decision.plan_gameweek_id, []).append(
                TRANSFER_ADAPTER.validate_python(
                    {
                        field: getattr(decision, field)
                        for field in TransferDecision.__dataclass_fields__
                    }
                )
            )
        return Plan(
            row.name,
            row.start_gameweek,
            row.end_gameweek,
            boundary,
            tuple(
                GameweekDecision(
                    week.gameweek_number,
                    LINEUP_ADAPTER.validate_python(week.slot_lineup),
                    tuple(transfers.get(week.id, [])),
                    Chip(week.planned_chip) if week.planned_chip is not None else None,
                )
                for week in weeks
                if row.start_gameweek <= week.gameweek_number <= row.end_gameweek
            ),
            row.revision,
        )

    def save_canonical(
        self,
        plan_id: int,
        plan: Plan,
        evaluation: PlanEvaluation,
        *,
        initial_sales: Mapping[UUID, int] | None = None,
    ) -> None:
        row = self.lock_plan(plan_id)
        row.name, row.start_gameweek, row.end_gameweek = (
            plan.name,
            plan.start_gameweek,
            plan.end_gameweek,
        )
        row.revision = plan.revision
        row.initial_bank_tenths = plan.boundary.bank_tenths
        row.starting_free_transfers = plan.boundary.free_transfers
        row.boundary_origin = plan.boundary.origin
        row.boundary_lineup = cast(
            list[dict[str, object]], LINEUP_ADAPTER.dump_python(plan.boundary.lineup, mode="json")
        )
        row.used_chips = sorted(chip.value for chip in plan.boundary.used_chips)
        row.free_hit_gameweek_19 = plan.boundary.free_hit_gameweek_19
        row.bank_assumptions = sorted(str(value) for value in plan.boundary.bank_assumptions)
        if row.foundation_state != "ready":
            row.initialization_version = 1
            row.initialized_at = dt.datetime.now(dt.UTC)
        else:
            row.updated_at = dt.datetime.now(dt.UTC)
        row.foundation_state = "ready"
        existing = self._session.scalars(
            select(PlanStartingPlayerModel)
            .where(PlanStartingPlayerModel.plan_id == plan_id)
            .order_by(PlanStartingPlayerModel.id)
        ).all()
        previous = tuple(
            Ownership(
                player.slot_id,
                player.ownership_id,
                player.player_id,
                player.purchase_price_tenths,
                PROVENANCE_ADAPTER.validate_python(player.provenance),
            )
            for player in existing
        )
        if previous != plan.boundary.players:
            self._session.execute(
                delete(PlanStartingPlayerModel).where(PlanStartingPlayerModel.plan_id == plan_id)
            )
            self._session.flush()
            self._session.add_all(
                [
                    PlanStartingPlayerModel(
                        plan_id=plan_id,
                        player_id=player.player_id,
                        slot_id=player.slot_id,
                        ownership_id=player.ownership_id,
                        purchase_price_tenths=player.purchase_price_tenths,
                        provenance=cast(
                            dict[str, object],
                            PROVENANCE_ADAPTER.dump_python(player.provenance, mode="json"),
                        ),
                    )
                    for player in plan.boundary.players
                ]
            )
        retained = {week.gameweek_number for week in plan.gameweeks}
        weeks = {
            week.gameweek_number: week
            for week in self._session.scalars(
                select(PlanGameweekModel).where(PlanGameweekModel.plan_id == plan_id)
            )
        }
        for number, removed_week in weeks.items():
            if number not in retained:
                self._session.delete(removed_week)
        self._session.flush()
        sales = dict(initial_sales or {})
        sales.update(
            {
                sale.decision_id: sale.selling_price_tenths
                for week in evaluation.gameweeks
                for sale in week.sales
            }
        )
        for week in plan.gameweeks:
            stored = weeks.get(week.gameweek_number)
            if stored is None:
                stored = PlanGameweekModel(plan_id=plan_id, gameweek_number=week.gameweek_number)
                self._session.add(stored)
                self._session.flush()
            stored.planned_chip = week.chip.value if week.chip is not None else None
            stored.slot_lineup = cast(
                list[dict[str, object]], LINEUP_ADAPTER.dump_python(week.lineup, mode="json")
            )
            old = self._session.scalars(
                select(PlanTransferDecisionModel)
                .where(PlanTransferDecisionModel.plan_gameweek_id == stored.id)
                .order_by(PlanTransferDecisionModel.decision_id)
            ).all()
            old_inputs = tuple(
                TRANSFER_ADAPTER.validate_python(
                    {
                        field: getattr(decision, field)
                        for field in TransferDecision.__dataclass_fields__
                    }
                )
                for decision in old
            )
            if old_inputs == week.transfers:
                for decision in old:
                    if decision.decision_id in sales:
                        decision.selling_price_tenths = sales[decision.decision_id]
                continue
            self._session.execute(
                delete(PlanTransferDecisionModel).where(
                    PlanTransferDecisionModel.plan_gameweek_id == stored.id
                )
            )
            self._session.flush()
            previous_sales = {
                decision.decision_id: decision.selling_price_tenths for decision in old
            }
            for transfer in week.transfers:
                sale = sales.get(transfer.decision_id, previous_sales.get(transfer.decision_id))
                if sale is None:
                    raise ValueError("Cannot materialize an unevaluated new sale")
                self._session.add(
                    PlanTransferDecisionModel(
                        plan_gameweek_id=stored.id,
                        selling_price_tenths=sale,
                        **{
                            field: getattr(transfer, field)
                            for field in TransferDecision.__dataclass_fields__
                        },
                    )
                )
        self._session.flush()

    def get_receipt(self, plan_id: int, mutation_id: UUID) -> PlanMutationModel | None:
        return self._session.scalar(
            select(PlanMutationModel)
            .where(
                PlanMutationModel.plan_id == plan_id, PlanMutationModel.mutation_id == mutation_id
            )
            .execution_options(populate_existing=True)
        )

    def accept_mutation(
        self,
        plan_id: int,
        mutation_id: UUID,
        *,
        digest: str,
        expected_revision: int,
        evaluator_version: str,
        rule_fingerprint: str,
        pending_inputs: dict[str, object],
    ) -> PlanMutationModel:
        self.lock_plan(plan_id)
        receipt = PlanMutationModel(
            plan_id=plan_id,
            mutation_id=mutation_id,
            digest=digest,
            expected_revision=expected_revision,
            status="validated_pending",
            evaluator_version=evaluator_version,
            rule_fingerprint=rule_fingerprint,
            pending_inputs=pending_inputs,
        )
        self._session.add(receipt)
        self._session.flush()
        return receipt

    def commit_mutation(self, receipt: PlanMutationModel, revision: int) -> None:
        self._session.execute(
            update(PlanMutationModel)
            .where(PlanMutationModel.id == receipt.id)
            .values(status="committed", pending_inputs=null(), committed_revision=revision)
            .execution_options(synchronize_session=False)
        )
        self._session.expire(receipt)
        self._session.flush()

    def list_plans(self) -> list[PlanSummaryRecord]:
        plans = self._session.execute(
            select(PlanModel).order_by(PlanModel.updated_at.desc())
        ).scalars()
        return [
            PlanSummaryRecord(
                plan_id=plan.id,
                name=plan.name,
                start_gameweek=plan.start_gameweek,
                end_gameweek=plan.end_gameweek,
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
            for plan in plans
        ]

    def get(self, plan_id: int) -> PlanRecord | None:
        plan = self._session.get(PlanModel, plan_id)
        if plan is None:
            return None

        gameweeks = list(
            self._session.execute(
                select(PlanGameweekModel)
                .where(PlanGameweekModel.plan_id == plan_id)
                .order_by(PlanGameweekModel.gameweek_number.asc())
            ).scalars()
        )
        players_by_gameweek = self._load_players({row.id: row for row in gameweeks})

        return PlanRecord(
            plan_id=plan.id,
            name=plan.name,
            start_gameweek=plan.start_gameweek,
            end_gameweek=plan.end_gameweek,
            initial_bank=float(plan.initial_bank),
            initial_free_transfers=plan.initial_free_transfers,
            gameweeks=[
                PlanGameweekRecord(
                    gameweek_number=gameweek.gameweek_number,
                    chip=gameweek.chip.value if gameweek.chip is not None else None,
                    bank=float(gameweek.bank),
                    free_transfers_available=gameweek.free_transfers_available,
                    transfers_made=gameweek.transfers_made,
                    points_hit=gameweek.points_hit,
                    players=players_by_gameweek.get(gameweek.id, []),
                )
                for gameweek in gameweeks
            ],
        )

    def create(
        self,
        *,
        name: str,
        start_gameweek: int,
        end_gameweek: int,
        initial_bank: float,
        initial_free_transfers: int,
    ) -> int:
        plan = PlanModel(
            name=name,
            start_gameweek=start_gameweek,
            end_gameweek=end_gameweek,
            initial_bank=initial_bank,
            initial_free_transfers=initial_free_transfers,
        )
        self._session.add(plan)
        self._session.flush()
        return plan.id

    def update_details(
        self,
        plan_id: int,
        *,
        name: str | None = None,
        start_gameweek: int | None = None,
        end_gameweek: int | None = None,
    ) -> None:
        plan = self._require(plan_id)
        if name is not None:
            plan.name = name
        if start_gameweek is not None:
            plan.start_gameweek = start_gameweek
        if end_gameweek is not None:
            plan.end_gameweek = end_gameweek
        plan.updated_at = dt.datetime.now(dt.UTC)
        self._session.flush()

    def delete(self, plan_id: int) -> None:
        plan = self._require(plan_id)
        self._session.delete(plan)
        self._session.flush()

    def delete_gameweeks_outside(self, plan_id: int, *, start: int, end: int) -> None:
        self._session.execute(
            delete(PlanGameweekModel).where(
                PlanGameweekModel.plan_id == plan_id,
                (PlanGameweekModel.gameweek_number < start)
                | (PlanGameweekModel.gameweek_number > end),
            )
        )
        self._session.flush()

    def save_gameweek(
        self,
        plan_id: int,
        gameweek_number: int,
        *,
        chip: str | None,
        bank: float,
        free_transfers_available: int,
        transfers_made: int,
        points_hit: int,
        players: list[PlanPlayerSave],
    ) -> None:
        plan = self._require(plan_id)
        gameweek = self._session.execute(
            select(PlanGameweekModel).where(
                PlanGameweekModel.plan_id == plan_id,
                PlanGameweekModel.gameweek_number == gameweek_number,
            )
        ).scalar_one_or_none()

        if gameweek is None:
            gameweek = PlanGameweekModel(plan_id=plan_id, gameweek_number=gameweek_number)
            self._session.add(gameweek)

        gameweek.chip = PlanChip(chip) if chip is not None else None
        gameweek.bank = bank
        gameweek.free_transfers_available = free_transfers_available
        gameweek.transfers_made = transfers_made
        gameweek.points_hit = points_hit
        self._session.flush()

        self._session.execute(
            delete(PlanGameweekPlayerModel).where(
                PlanGameweekPlayerModel.plan_gameweek_id == gameweek.id
            )
        )
        self._session.add_all(
            [
                PlanGameweekPlayerModel(
                    plan_gameweek_id=gameweek.id,
                    player_id=player.player_id,
                    is_starting=player.is_starting,
                    bench_order=player.bench_order,
                    is_captain=player.is_captain,
                    is_vice_captain=player.is_vice_captain,
                )
                for player in players
            ]
        )
        plan.updated_at = dt.datetime.now(dt.UTC)
        self._session.flush()

    def update_accounting(self, plan_id: int, entries: list[PlanGameweekAccounting]) -> None:
        if not entries:
            return

        by_number = {entry.gameweek_number: entry for entry in entries}
        gameweeks = self._session.execute(
            select(PlanGameweekModel).where(
                PlanGameweekModel.plan_id == plan_id,
                PlanGameweekModel.gameweek_number.in_(by_number.keys()),
            )
        ).scalars()

        for gameweek in gameweeks:
            entry = by_number[gameweek.gameweek_number]
            gameweek.bank = entry.bank
            gameweek.free_transfers_available = entry.free_transfers_available
            gameweek.transfers_made = entry.transfers_made
            gameweek.points_hit = entry.points_hit
        self._session.flush()

    def _require(self, plan_id: int) -> PlanModel:
        plan = self._session.get(PlanModel, plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan

    def _load_players(
        self, gameweeks_by_id: dict[int, PlanGameweekModel]
    ) -> dict[int, list[PlanPlayerRecord]]:
        if not gameweeks_by_id:
            return {}

        rows = self._session.execute(
            select(
                PlanGameweekPlayerModel.plan_gameweek_id,
                PlayerModel.id,
                PlayerModel.web_name,
                PlayerModel.first_name,
                PlayerModel.second_name,
                TeamModel.id,
                TeamModel.name,
                TeamModel.short_name,
                PlayerModel.position,
                PlayerModel.current_price,
                PlayerModel.status,
                PlanGameweekPlayerModel.is_starting,
                PlanGameweekPlayerModel.bench_order,
                PlanGameweekPlayerModel.is_captain,
                PlanGameweekPlayerModel.is_vice_captain,
            )
            .join(PlayerModel, PlayerModel.id == PlanGameweekPlayerModel.player_id)
            .join(TeamModel, TeamModel.id == PlayerModel.team_id)
            .where(PlanGameweekPlayerModel.plan_gameweek_id.in_(gameweeks_by_id.keys()))
            .order_by(
                PlanGameweekPlayerModel.is_starting.desc(),
                PlanGameweekPlayerModel.bench_order.asc().nulls_last(),
                PlayerModel.web_name.asc(),
            )
        ).all()

        players_by_gameweek: dict[int, list[PlanPlayerRecord]] = {}
        for row in rows:
            players_by_gameweek.setdefault(row[0], []).append(
                PlanPlayerRecord(
                    player_id=row[1],
                    web_name=row[2],
                    first_name=row[3],
                    second_name=row[4],
                    team_id=row[5],
                    team_name=row[6],
                    team_short_name=row[7],
                    position=row[8].value if hasattr(row[8], "value") else str(row[8]),
                    current_price=float(row[9]),
                    status=row[10],
                    is_starting=row[11],
                    bench_order=row[12],
                    is_captain=row[13],
                    is_vice_captain=row[14],
                )
            )
        return players_by_gameweek
