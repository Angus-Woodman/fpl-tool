from api.repositories.gameweek_read_repository import GameweekReadItem
from api.services.list_gameweeks import ListGameweeksService


class _FakeGameweekReadRepository:
    def list_gameweeks(self) -> list[GameweekReadItem]:
        return [
            GameweekReadItem(
                id=1,
                number=1,
                name="Gameweek 1",
                is_current=False,
                is_next=True,
                is_finished=False,
            )
        ]


def test_list_gameweeks_service_returns_items_and_total() -> None:
    service = ListGameweeksService(_FakeGameweekReadRepository())

    result = service.execute()

    assert result.total == 1
    assert result.items[0].number == 1
