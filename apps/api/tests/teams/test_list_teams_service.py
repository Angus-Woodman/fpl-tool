from api.repositories.team_read_repository import TeamReadItem
from api.services.list_teams import ListTeamsService


class _FakeTeamReadRepository:
    def list_teams(self) -> list[TeamReadItem]:
        return [
            TeamReadItem(id=1, name="Arsenal", short_name="ARS", difficulty=4),
            TeamReadItem(id=2, name="Aston Villa", short_name="AVL", difficulty=2),
        ]


def test_list_teams_service_returns_items_and_total() -> None:
    service = ListTeamsService(_FakeTeamReadRepository())

    result = service.execute()

    assert result.total == 2
    assert result.items[0].name == "Arsenal"
