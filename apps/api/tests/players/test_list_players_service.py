from api.repositories.player_read_repository import PlayerQuery, PlayerQueryResult, PlayerReadItem
from api.services.list_players import ListPlayersRequest, ListPlayersService


class _FakeRepository:
    def __init__(self) -> None:
        self.received_query: PlayerQuery | None = None

    def list_players(self, query: PlayerQuery) -> PlayerQueryResult:
        self.received_query = query
        return PlayerQueryResult(
            items=[
                PlayerReadItem(
                    id=1,
                    web_name="Saka",
                    first_name="Bukayo",
                    second_name="Saka",
                    team_name="Arsenal",
                    team_short_name="ARS",
                    position="MID",
                    current_price=10.5,
                    status="a",
                )
            ],
            total=1,
            page=query.page,
            page_size=query.page_size,
        )


def test_list_players_service_passes_request_to_repository() -> None:
    repository = _FakeRepository()
    service = ListPlayersService(repository)

    result = service.execute(
        ListPlayersRequest(
            search="sak",
            position="MID",
            team_id=2,
            status="a",
            sort="price_desc",
            page=2,
            page_size=20,
        )
    )

    assert repository.received_query is not None
    assert repository.received_query.search == "sak"
    assert repository.received_query.position == "MID"
    assert repository.received_query.team_id == 2
    assert repository.received_query.sort == "price_desc"
    assert result.total == 1
