from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from api.repositories.current_squad_repository import (
    CurrentSquadPlayerSave,
    CurrentSquadRecord,
)
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem


class CurrentSquadRepositoryPort(Protocol):
    def get_current(self) -> CurrentSquadRecord | None: ...

    def save_current(
        self,
        *,
        bank: float,
        free_transfers: int,
        players: list[CurrentSquadPlayerSave],
    ) -> CurrentSquadRecord: ...


class SquadPlayerLookupRepositoryPort(Protocol):
    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]: ...


@dataclass(frozen=True)
class CurrentSquadPlayerSelection:
    player_id: int
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


@dataclass(frozen=True)
class UpsertCurrentSquadRequest:
    bank: float
    free_transfers: int
    players: list[CurrentSquadPlayerSelection]


class GetCurrentSquadService:
    def __init__(self, repository: CurrentSquadRepositoryPort) -> None:
        self._repository = repository

    def execute(self) -> CurrentSquadRecord | None:
        return self._repository.get_current()


class UpsertCurrentSquadService:
    def __init__(
        self,
        repository: CurrentSquadRepositoryPort,
        player_lookup_repository: SquadPlayerLookupRepositoryPort,
    ) -> None:
        self._repository = repository
        self._player_lookup_repository = player_lookup_repository

    def execute(self, request: UpsertCurrentSquadRequest) -> CurrentSquadRecord:
        self._validate(request)
        return self._repository.save_current(
            bank=request.bank,
            free_transfers=request.free_transfers,
            players=[
                CurrentSquadPlayerSave(
                    player_id=player.player_id,
                    is_starting=player.is_starting,
                    bench_order=player.bench_order,
                    is_captain=player.is_captain,
                    is_vice_captain=player.is_vice_captain,
                )
                for player in request.players
            ],
        )

    def _validate(self, request: UpsertCurrentSquadRequest) -> None:
        if len(request.players) != 15:
            raise ValueError("Squad must contain exactly 15 players")

        player_ids = [player.player_id for player in request.players]
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("Squad cannot contain duplicate players")

        player_map = {
            player.player_id: player
            for player in self._player_lookup_repository.get_by_ids(player_ids)
        }
        if len(player_map) != len(player_ids):
            raise ValueError("Squad contains unknown players")

        starters = [player for player in request.players if player.is_starting]
        bench = [player for player in request.players if not player.is_starting]

        if len(starters) != 11:
            raise ValueError("Squad must contain exactly 11 starting players")
        if len(bench) != 4:
            raise ValueError("Squad must contain exactly 4 bench players")

        bench_orders = {player.bench_order for player in bench}
        if bench_orders != {1, 2, 3, 4}:
            raise ValueError("Bench players must use bench order 1, 2, 3, and 4")
        if any(player.bench_order is not None for player in starters):
            raise ValueError("Starting players cannot have a bench order")

        captains = [player for player in request.players if player.is_captain]
        vice_captains = [player for player in request.players if player.is_vice_captain]

        if len(captains) != 1:
            raise ValueError("Squad must contain exactly one captain")
        if len(vice_captains) != 1:
            raise ValueError("Squad must contain exactly one vice-captain")
        if captains[0].player_id == vice_captains[0].player_id:
            raise ValueError("Captain and vice-captain must be different players")

        positions = Counter(player_map[player.player_id].position for player in request.players)
        if positions != {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}:
            raise ValueError("Squad must contain 2 GK, 5 DEF, 5 MID, and 3 FWD")

        teams = Counter(player_map[player.player_id].team_id for player in request.players)
        if any(count > 3 for count in teams.values()):
            raise ValueError("Squad cannot contain more than three players from one team")
