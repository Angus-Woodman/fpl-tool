from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.repositories.fixture_read_repository import FixtureTickerResult


class FixtureReadRepositoryPort(Protocol):
    def list_upcoming(
        self,
        *,
        page: int,
        page_size: int,
        team_id: int | None,
        gameweek: int | None,
    ) -> FixtureTickerResult: ...


@dataclass(frozen=True)
class ListFixtureTickerRequest:
    page: int
    page_size: int
    team_id: int | None = None
    gameweek: int | None = None


class ListFixtureTickerService:
    def __init__(self, repository: FixtureReadRepositoryPort) -> None:
        self._repository = repository

    def execute(self, request: ListFixtureTickerRequest) -> FixtureTickerResult:
        return self._repository.list_upcoming(
            page=request.page,
            page_size=request.page_size,
            team_id=request.team_id,
            gameweek=request.gameweek,
        )
