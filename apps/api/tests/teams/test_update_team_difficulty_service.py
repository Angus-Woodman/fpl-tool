from api.repositories.team_read_repository import TeamReadItem
from api.services.update_team_difficulty import (
    UpdateTeamDifficultyRequest,
    UpdateTeamDifficultyService,
)


class _FakeTeamWriteRepository:
    def __init__(self, result: TeamReadItem | None) -> None:
        self._result = result
        self.last_team_id: int | None = None
        self.last_difficulty: int | None = None

    def update_difficulty(self, team_id: int, difficulty: int) -> TeamReadItem | None:
        self.last_team_id = team_id
        self.last_difficulty = difficulty
        return self._result


def test_update_team_difficulty_service_returns_updated_team() -> None:
    repository = _FakeTeamWriteRepository(
        TeamReadItem(id=1, name="Arsenal", short_name="ARS", difficulty=5)
    )
    service = UpdateTeamDifficultyService(repository)

    result = service.execute(UpdateTeamDifficultyRequest(team_id=1, difficulty=5))

    assert repository.last_team_id == 1
    assert repository.last_difficulty == 5
    assert result is not None
    assert result.difficulty == 5


def test_update_team_difficulty_service_returns_none_when_team_missing() -> None:
    repository = _FakeTeamWriteRepository(None)
    service = UpdateTeamDifficultyService(repository)

    result = service.execute(UpdateTeamDifficultyRequest(team_id=999, difficulty=3))

    assert result is None
