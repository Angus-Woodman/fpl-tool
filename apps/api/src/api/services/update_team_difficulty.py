from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from api.repositories.team_read_repository import TeamReadItem


class TeamWriteRepositoryPort(Protocol):
    def update_difficulty(self, team_id: int, difficulty: int) -> TeamReadItem | None: ...


@dataclass(frozen=True)
class UpdateTeamDifficultyRequest:
    team_id: int
    difficulty: int


class UpdateTeamDifficultyService:
    def __init__(self, repository: TeamWriteRepositoryPort) -> None:
        self._repository = repository

    def execute(self, request: UpdateTeamDifficultyRequest) -> TeamReadItem | None:
        return self._repository.update_difficulty(request.team_id, request.difficulty)
