from api.repositories.fixture_read_repository import FixtureTickerItem, FixtureTickerResult
from api.services.list_fixtures import ListFixtureTickerRequest, ListFixtureTickerService


class _FakeFixtureReadRepository:
    def __init__(self) -> None:
        self.last_limit: int | None = None

    def list_upcoming(self, limit: int) -> FixtureTickerResult:
        self.last_limit = limit
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
        )


def test_list_fixture_ticker_service_passes_limit() -> None:
    repository = _FakeFixtureReadRepository()
    service = ListFixtureTickerService(repository)

    result = service.execute(ListFixtureTickerRequest(limit=5))

    assert repository.last_limit == 5
    assert result.total == 1
    assert result.items[0].away_team_short_name == "MCI"
