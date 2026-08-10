import pytest
from api.adapters.fpl.schemas import BootstrapStaticDto, FplFixtureDto
from api.core.exceptions import DataMappingError
from api.services.import_fpl_data import ImportFplDataService


class _FakeProvider:
    def __init__(self, payload: BootstrapStaticDto, fixtures: list[dict[str, object]]) -> None:
        self._payload = payload
        self._fixtures = fixtures

    def fetch_bootstrap_static(self) -> BootstrapStaticDto:
        return self._payload

    def fetch_fixtures(self) -> list[FplFixtureDto]:
        return [FplFixtureDto.model_validate(item) for item in self._fixtures]


class _FakeTeamRepository:
    def __init__(self, team_map: dict[int, int]) -> None:
        self._team_map = team_map
        self.upserted_teams = 0

    def upsert_many(self, teams: list[object]) -> None:
        self.upserted_teams = len(teams)

    def get_internal_ids_by_external_ids(self, external_ids: set[int]) -> dict[int, int]:
        return {
            external_id: self._team_map[external_id]
            for external_id in external_ids
            if external_id in self._team_map
        }


class _FakePlayerRepository:
    def __init__(self) -> None:
        self.upserted_players = 0

    def upsert_many(self, players: list[object]) -> None:
        self.upserted_players = len(players)


class _FakeGameweekRepository:
    def __init__(self, gameweek_map: dict[int, int]) -> None:
        self.upserted_gameweeks = 0
        self._gameweek_map = gameweek_map

    def upsert_many(self, gameweeks: list[object]) -> None:
        self.upserted_gameweeks = len(gameweeks)

    def get_internal_ids_by_numbers(self, numbers: set[int]) -> dict[int, int]:
        return {
            number: self._gameweek_map[number]
            for number in numbers
            if number in self._gameweek_map
        }


class _FakeFixtureRepository:
    def __init__(self) -> None:
        self.upserted_fixtures = 0

    def upsert_many(self, fixtures: list[object]) -> None:
        self.upserted_fixtures = len(fixtures)


@pytest.fixture
def bootstrap_payload() -> BootstrapStaticDto:
    return BootstrapStaticDto.model_validate(
        {
            "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
            "elements": [
                {
                    "id": 7,
                    "first_name": "Kai",
                    "second_name": "Havertz",
                    "web_name": "Havertz",
                    "team": 1,
                    "element_type": 4,
                    "now_cost": 90,
                    "status": "a",
                }
            ],
            "events": [
                {
                    "id": 1,
                    "name": "Gameweek 1",
                    "deadline_time": "2026-08-14T18:30:00Z",
                    "is_current": False,
                    "is_next": True,
                    "is_finished": False,
                }
            ],
        }
    )


@pytest.fixture
def fixture_payload() -> list[dict[str, object]]:
    return [
        {
            "id": 1001,
            "event": 1,
            "team_h": 1,
            "team_a": 1,
            "kickoff_time": "2026-08-16T15:00:00Z",
            "team_h_score": None,
            "team_a_score": None,
            "finished": False,
        }
    ]


def test_import_service_returns_summary(
    bootstrap_payload: BootstrapStaticDto,
    fixture_payload: list[dict[str, object]],
) -> None:
    team_repo = _FakeTeamRepository({1: 101})
    player_repo = _FakePlayerRepository()
    gameweek_repo = _FakeGameweekRepository({1: 201})
    fixture_repo = _FakeFixtureRepository()

    service = ImportFplDataService(
        provider=_FakeProvider(bootstrap_payload, fixture_payload),
        team_repository=team_repo,
        player_repository=player_repo,
        gameweek_repository=gameweek_repo,
        fixture_repository=fixture_repo,
    )

    summary = service.import_bootstrap_static()

    assert summary.teams_imported == 1
    assert summary.players_imported == 1
    assert summary.gameweeks_imported == 1
    assert summary.fixtures_imported == 1
    assert team_repo.upserted_teams == 1
    assert player_repo.upserted_players == 1
    assert gameweek_repo.upserted_gameweeks == 1
    assert fixture_repo.upserted_fixtures == 1


def test_import_service_fails_when_team_mapping_missing(
    bootstrap_payload: BootstrapStaticDto,
    fixture_payload: list[dict[str, object]],
) -> None:
    service = ImportFplDataService(
        provider=_FakeProvider(bootstrap_payload, fixture_payload),
        team_repository=_FakeTeamRepository({}),
        player_repository=_FakePlayerRepository(),
        gameweek_repository=_FakeGameweekRepository({1: 201}),
        fixture_repository=_FakeFixtureRepository(),
    )

    with pytest.raises(DataMappingError):
        service.import_bootstrap_static()
