from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from api.repositories.current_squad_repository import CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord


@dataclass(frozen=True)
class HorizonProjectionTotals:
    horizon_1: float
    horizon_3: float
    horizon_5: float


@dataclass(frozen=True)
class MyTeamPlayerViewRecord:
    player_id: int
    web_name: str
    first_name: str
    second_name: str
    team_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool
    projection_totals: HorizonProjectionTotals | None


@dataclass(frozen=True)
class MyTeamViewRecord:
    squad_id: int
    name: str
    bank: float
    free_transfers: int
    players: list[MyTeamPlayerViewRecord]
    projection_totals: HorizonProjectionTotals | None
    bench_projection_totals: HorizonProjectionTotals | None
    captain_adjusted_projection_totals: HorizonProjectionTotals | None


class CurrentSquadRepositoryPort(Protocol):
    def get_current(self) -> CurrentSquadRecord | None: ...


class MyTeamProjectionRepositoryPort(Protocol):
    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]: ...


class GetMyTeamViewService:
    def __init__(
        self,
        current_squad_repository: CurrentSquadRepositoryPort,
        projection_repository: MyTeamProjectionRepositoryPort,
    ) -> None:
        self._current_squad_repository = current_squad_repository
        self._projection_repository = projection_repository

    def execute(self) -> MyTeamViewRecord | None:
        current_squad = self._current_squad_repository.get_current()
        if current_squad is None:
            return None

        player_ids = [player.player_id for player in current_squad.players]
        projection_rows = self._projection_repository.list_latest_player_fixture_projections(
            player_ids
        )
        totals_by_player = self._build_totals_by_player(projection_rows)

        players = [
            MyTeamPlayerViewRecord(
                player_id=player.player_id,
                web_name=player.web_name,
                first_name=player.first_name,
                second_name=player.second_name,
                team_name=player.team_name,
                team_short_name=player.team_short_name,
                position=player.position,
                current_price=player.current_price,
                status=player.status,
                is_starting=player.is_starting,
                bench_order=player.bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
                projection_totals=totals_by_player.get(player.player_id),
            )
            for player in current_squad.players
        ]

        starters = [player for player in players if player.is_starting]
        bench = [player for player in players if not player.is_starting]
        captain = next((player for player in players if player.is_captain), None)

        projection_totals = self._sum_horizons([player.projection_totals for player in starters])
        bench_projection_totals = self._sum_horizons([player.projection_totals for player in bench])
        captain_adjusted_projection_totals = self._sum_horizons(
            [player.projection_totals for player in starters]
            + ([captain.projection_totals] if captain is not None else [])
        )

        return MyTeamViewRecord(
            squad_id=current_squad.squad_id,
            name=current_squad.name,
            bank=current_squad.bank,
            free_transfers=current_squad.free_transfers,
            players=players,
            projection_totals=projection_totals,
            bench_projection_totals=bench_projection_totals,
            captain_adjusted_projection_totals=captain_adjusted_projection_totals,
        )

    def _build_totals_by_player(
        self, rows: list[PlayerProjectionFixtureRecord]
    ) -> dict[int, HorizonProjectionTotals]:
        totals_by_player_gameweek: dict[int, dict[int, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for row in rows:
            totals_by_player_gameweek[row.player_id][row.gameweek_number] += row.projected_points

        return {
            player_id: self._calculate_horizons(gameweek_totals)
            for player_id, gameweek_totals in totals_by_player_gameweek.items()
        }

    def _calculate_horizons(self, gameweek_totals: dict[int, float]) -> HorizonProjectionTotals:
        ordered_totals = [gameweek_totals[number] for number in sorted(gameweek_totals)]
        return HorizonProjectionTotals(
            horizon_1=sum(ordered_totals[:1]),
            horizon_3=sum(ordered_totals[:3]),
            horizon_5=sum(ordered_totals[:5]),
        )

    def _sum_horizons(
        self, items: list[HorizonProjectionTotals | None]
    ) -> HorizonProjectionTotals | None:
        populated = [item for item in items if item is not None]
        if not populated:
            return None

        return HorizonProjectionTotals(
            horizon_1=sum(item.horizon_1 for item in populated),
            horizon_3=sum(item.horizon_3 for item in populated),
            horizon_5=sum(item.horizon_5 for item in populated),
        )
