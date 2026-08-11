from api.repositories.current_squad_repository import CurrentSquadPlayerRecord, CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.services.get_my_team_view import GetMyTeamViewService


class _FakeCurrentSquadRepository:
    def get_current(self) -> CurrentSquadRecord | None:
        return CurrentSquadRecord(
            squad_id=1,
            name="My Team",
            bank=1.5,
            free_transfers=2,
            players=[
                CurrentSquadPlayerRecord(
                    player_id=1,
                    web_name="Saka",
                    first_name="Bukayo",
                    second_name="Saka",
                    team_name="Arsenal",
                    team_short_name="ARS",
                    position="MID",
                    current_price=10.5,
                    status="a",
                    is_starting=True,
                    bench_order=None,
                    is_captain=True,
                    is_vice_captain=False,
                ),
                CurrentSquadPlayerRecord(
                    player_id=2,
                    web_name="Watkins",
                    first_name="Ollie",
                    second_name="Watkins",
                    team_name="Aston Villa",
                    team_short_name="AVL",
                    position="FWD",
                    current_price=9.0,
                    status="a",
                    is_starting=True,
                    bench_order=None,
                    is_captain=False,
                    is_vice_captain=True,
                ),
                CurrentSquadPlayerRecord(
                    player_id=3,
                    web_name="Turner",
                    first_name="Matt",
                    second_name="Turner",
                    team_name="Forest",
                    team_short_name="NFO",
                    position="GK",
                    current_price=4.0,
                    status="a",
                    is_starting=False,
                    bench_order=1,
                    is_captain=False,
                    is_vice_captain=False,
                ),
            ],
        )


class _FakeProjectionRepository:
    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]:
        assert player_ids == [1, 2, 3]
        return [
            PlayerProjectionFixtureRecord(player_id=1, gameweek_number=2, projected_points=5.0),
            PlayerProjectionFixtureRecord(player_id=1, gameweek_number=3, projected_points=6.0),
            PlayerProjectionFixtureRecord(player_id=1, gameweek_number=4, projected_points=4.0),
            PlayerProjectionFixtureRecord(player_id=2, gameweek_number=2, projected_points=4.5),
            PlayerProjectionFixtureRecord(player_id=2, gameweek_number=3, projected_points=3.5),
            PlayerProjectionFixtureRecord(player_id=3, gameweek_number=2, projected_points=2.0),
        ]


def test_get_my_team_view_service_combines_squad_and_horizon_totals() -> None:
    service = GetMyTeamViewService(_FakeCurrentSquadRepository(), _FakeProjectionRepository())

    result = service.execute()

    assert result is not None
    assert result.players[0].projection_totals is not None
    assert result.players[0].projection_totals.horizon_1 == 5.0
    assert result.players[0].projection_totals.horizon_3 == 15.0
    assert result.projection_totals is not None
    assert result.projection_totals.horizon_1 == 9.5
    assert result.projection_totals.horizon_3 == 23.0
    assert result.bench_projection_totals is not None
    assert result.bench_projection_totals.horizon_1 == 2.0
    assert result.captain_adjusted_projection_totals is not None
    assert result.captain_adjusted_projection_totals.horizon_1 == 14.5
