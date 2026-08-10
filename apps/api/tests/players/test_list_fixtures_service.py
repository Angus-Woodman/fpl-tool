from api.repositories.fixture_read_repository import FixtureTickerItem, FixtureTickerResult
from api.services.list_fixtures import ListFixtureTickerRequest, ListFixtureTickerService


class _FakeFixtureReadRepository:
    def __init__(self) -> None:
        self.last_page: int | None = None
        self.last_page_size: int | None = None
        self.last_team_id: int | None = None
        self.last_gameweek: int | None = None

    def list_upcoming(
        self,
        *,
        page: int,
        page_size: int,
        team_id: int | None,
        gameweek: int | None,
    ) -> FixtureTickerResult:
        self.last_page = page
        self.last_page_size = page_size
        self.last_team_id = team_id
        self.last_gameweek = gameweek
        return FixtureTickerResult(
            items=[
                FixtureTickerItem(
                    fixture_id=10,
                    gameweek_number=3,
                    kickoff_time="2026-08-28T18:30:00+00:00",
                    home_team_short_name="LIV",
                    away_team_short_name="MCI",
                    finished=False,
                )
            ],
            total=1,
            page=page,
            page_size=page_size,
        )


def test_list_fixture_ticker_service_passes_limit() -> None:
    repository = _FakeFixtureReadRepository()
    service = ListFixtureTickerService(repository)

    result = service.execute(ListFixtureTickerRequest(page=2, page_size=5, team_id=4, gameweek=7))

    assert repository.last_page == 2
    assert repository.last_page_size == 5
    assert repository.last_team_id == 4
    assert repository.last_gameweek == 7
    assert result.total == 1
    assert result.page == 2
    assert result.page_size == 5
    assert result.items[0].away_team_short_name == "MCI"
