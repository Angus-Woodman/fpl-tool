from api.repositories.team_read_repository import TeamReadItem
from api.services.list_teams import ListTeamsService


class _FakeTeamReadRepository:
    def list_teams(self) -> list[TeamReadItem]:
        return [
            TeamReadItem(
                id=1,
                name="Arsenal",
                short_name="ARS",
                difficulty=4,
                source_difficulty=4,
                difficulty_override=None,
            ),
            TeamReadItem(
                id=2,
                name="Aston Villa",
                short_name="AVL",
                difficulty=2,
                source_difficulty=2,
                difficulty_override=None,
            ),
        ]


def test_list_teams_service_returns_items_and_total() -> None:
    service = ListTeamsService(_FakeTeamReadRepository())

    result = service.execute()

    assert result.total == 2
    assert result.items[0].name == "Arsenal"
