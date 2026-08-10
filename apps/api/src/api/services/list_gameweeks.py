from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.repositories.gameweek_read_repository import GameweekReadItem


class GameweekReadRepositoryPort(Protocol):
    def list_gameweeks(self) -> list[GameweekReadItem]: ...


@dataclass(frozen=True)
class GameweekListResult:
    items: list[GameweekReadItem]
    total: int


class ListGameweeksService:
    def __init__(self, repository: GameweekReadRepositoryPort) -> None:
        self._repository = repository

    def execute(self) -> GameweekListResult:
        items = self._repository.list_gameweeks()
        return GameweekListResult(items=items, total=len(items))
