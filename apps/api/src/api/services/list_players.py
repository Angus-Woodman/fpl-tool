from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.repositories.player_read_repository import PlayerQuery, PlayerQueryResult


class PlayerReadRepositoryPort(Protocol):
    def list_players(self, query: PlayerQuery) -> PlayerQueryResult: ...


@dataclass(frozen=True)
class ListPlayersRequest:
    search: str | None
    position: str | None
    team_id: int | None
    status: str | None
    sort: str
    page: int
    page_size: int


class ListPlayersService:
    def __init__(self, repository: PlayerReadRepositoryPort) -> None:
        self._repository = repository

    def execute(self, request: ListPlayersRequest) -> PlayerQueryResult:
        return self._repository.list_players(
            PlayerQuery(
                search=request.search,
                position=request.position,
                team_id=request.team_id,
                status=request.status,
                sort=request.sort,
                page=request.page,
                page_size=request.page_size,
            )
        )
