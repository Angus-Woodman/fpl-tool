from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.repositories.fixture_read_repository import FixtureTickerResult


class FixtureReadRepositoryPort(Protocol):
    def list_upcoming(self, limit: int) -> FixtureTickerResult: ...


@dataclass(frozen=True)
class ListFixtureTickerRequest:
    limit: int


class ListFixtureTickerService:
    def __init__(self, repository: FixtureReadRepositoryPort) -> None:
        self._repository = repository

    def execute(self, request: ListFixtureTickerRequest) -> FixtureTickerResult:
        return self._repository.list_upcoming(limit=request.limit)
