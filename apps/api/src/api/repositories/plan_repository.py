from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.models import (
    PlanChip,
    PlanGameweekModel,
    PlanGameweekPlayerModel,
    PlanModel,
    PlayerModel,
    TeamModel,
)


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
    bank: float
    free_transfers_available: int
    transfers_made: int
    points_hit: int
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
