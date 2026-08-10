from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.repositories.team_read_repository import TeamReadItem


class TeamReadRepositoryPort(Protocol):
    def list_teams(self) -> list[TeamReadItem]: ...


@dataclass(frozen=True)
class TeamListResult:
    items: list[TeamReadItem]
    total: int


class ListTeamsService:
    def __init__(self, repository: TeamReadRepositoryPort) -> None:
        self._repository = repository

    def execute(self) -> TeamListResult:
        items = self._repository.list_teams()
        return TeamListResult(items=items, total=len(items))
