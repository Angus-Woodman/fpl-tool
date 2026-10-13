from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import SquadSlot, validate_squad

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

        # Squad shape, captaincy, club limit and starting formation are the domain's rules.
        validate_squad(
            [
                SquadSlot(
                    player_id=player.player_id,
                    position=PlayerPosition(player_map[player.player_id].position),
                    team_id=player_map[player.player_id].team_id,
                    is_starting=player.is_starting,
                    bench_order=player.bench_order,
                    is_captain=player.is_captain,
                    is_vice_captain=player.is_vice_captain,
                )
                for player in request.players
            ]
        )
