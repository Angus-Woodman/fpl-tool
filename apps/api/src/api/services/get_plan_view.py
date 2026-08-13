from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import Chip, SquadSlot, has_unlimited_transfers, score_gameweek

from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.plan_repository import PlanRecord


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


@dataclass(frozen=True)
class PlanTransferViewRecord:
    player_id: int
    web_name: str


@dataclass(frozen=True)
class PlanGameweekViewRecord:
    gameweek_number: int
    chip: str | None
    bank: float
    free_transfers_available: int
    unlimited_transfers: bool
    transfers_made: int
    points_hit: int
    starting_points: float
    bench_points: float
    captain_bonus_points: float
    total_points: float
    players: list[PlanPlayerViewRecord]
    transfers_in: list[PlanTransferViewRecord]
    transfers_out: list[PlanTransferViewRecord]


@dataclass(frozen=True)
class PlanViewRecord:
    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int
    initial_bank: float
    initial_free_transfers: int
    total_points: float
    total_points_hit: int
    gameweeks: list[PlanGameweekViewRecord]


class PlanProjectionRepositoryPort(Protocol):
    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]: ...


class GetPlanViewService:
    def __init__(self, projection_repository: PlanProjectionRepositoryPort) -> None:
        self._projection_repository = projection_repository

    def execute(self, plan: PlanRecord) -> PlanViewRecord:
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
        previous_ids: set[int] | None = None
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
                points_hit=gameweek.points_hit,
            )

            current_ids = {player.player_id for player in gameweek.players}
            incoming = sorted(current_ids - previous_ids) if previous_ids else []
            outgoing = sorted(previous_ids - current_ids) if previous_ids else []
            previous_ids = current_ids

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
            total_points=round(sum(item.total_points for item in gameweeks), 2),
            total_points_hit=sum(item.points_hit for item in gameweeks),
            gameweeks=gameweeks,
        )


__all__ = [
    "GetPlanViewService",
    "PlanFixtureViewRecord",
    "PlanGameweekViewRecord",
    "PlanPlayerViewRecord",
    "PlanTransferViewRecord",
    "PlanViewRecord",
]
