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
            PlayerProjectionFixtureRecord(
                player_id=1,
                fixture_id=101,
                gameweek_number=2,
                projected_points=5.0,
                kickoff_time="2026-08-15T15:00:00+00:00",
                opponent_team_short_name="CHE",
                is_home=True,
            ),
            PlayerProjectionFixtureRecord(
                player_id=1,
                fixture_id=102,
                gameweek_number=3,
                projected_points=6.0,
                kickoff_time="2026-08-22T15:00:00+00:00",
                opponent_team_short_name="TOT",
                is_home=False,
            ),
            PlayerProjectionFixtureRecord(
                player_id=1,
                fixture_id=103,
                gameweek_number=4,
                projected_points=4.0,
                kickoff_time="2026-08-29T15:00:00+00:00",
                opponent_team_short_name="MCI",
                is_home=True,
            ),
            PlayerProjectionFixtureRecord(
                player_id=2,
                fixture_id=201,
                gameweek_number=2,
                projected_points=4.5,
                kickoff_time="2026-08-15T15:00:00+00:00",
                opponent_team_short_name="BHA",
                is_home=False,
            ),
            PlayerProjectionFixtureRecord(
                player_id=2,
                fixture_id=202,
                gameweek_number=3,
                projected_points=3.5,
                kickoff_time="2026-08-22T15:00:00+00:00",
                opponent_team_short_name="NEW",
                is_home=True,
            ),
            PlayerProjectionFixtureRecord(
                player_id=3,
                fixture_id=301,
                gameweek_number=2,
                projected_points=2.0,
                kickoff_time="2026-08-15T15:00:00+00:00",
                opponent_team_short_name="LIV",
                is_home=False,
            ),
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
    assert result.gameweek_numbers == [2, 3, 4]
    assert result.players[0].fixture_projections[0].opponent_team_short_name == "CHE"


_FULL_POSITIONS = ["GK"] + ["DEF"] * 4 + ["MID"] * 4 + ["FWD"] * 2 + ["GK", "DEF", "MID", "FWD"]


class _FullSquadRepository:
    """A legal 4-4-2 with captain 2, vice-captain 3 and bench GK/DEF/MID/FWD."""

    def get_current(self) -> CurrentSquadRecord | None:
        return CurrentSquadRecord(
            squad_id=1,
            name="My Team",
            bank=1.5,
            free_transfers=2,
            players=[
                CurrentSquadPlayerRecord(
                    player_id=index + 1,
                    web_name=f"P{index + 1}",
                    first_name="First",
                    second_name=f"P{index + 1}",
                    team_name=f"Team {index % 5 + 1}",
                    team_short_name=f"T{index % 5 + 1}",
                    position=position,
                    current_price=5.0,
                    status="a",
                    is_starting=index < 11,
                    bench_order=None if index < 11 else index - 10,
                    is_captain=index == 1,
                    is_vice_captain=index == 2,
                    team_id=index % 5 + 1,
                )
                for index, position in enumerate(_FULL_POSITIONS)
            ],
        )


class _NoProjectionRepository:
    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]:
        return []


def test_us6_my_team_view_offers_the_engine_legal_rearrangements() -> None:
    from fpl_engine.domain import PlayerPosition
    from fpl_engine.rules import SquadSlot, legal_rearrangements

    result = GetMyTeamViewService(_FullSquadRepository(), _NoProjectionRepository()).execute()

    assert result is not None
    expected = legal_rearrangements(
        [
            SquadSlot(
                player.player_id,
                PlayerPosition(player.position),
                player.team_id,
                player.is_starting,
                player.bench_order,
                player.is_captain,
                player.is_vice_captain,
            )
            for player in _FullSquadRepository().get_current().players  # type: ignore[union-attr]
        ]
    )
    assert expected
    assert result.legal_rearrangements == expected
    offered = {
        (frozenset({choice.first_player_id, choice.second_player_id}), choice.kind)
        for choice in result.legal_rearrangements
    }
    assert (frozenset({1, 12}), "substitution") in offered
    assert (frozenset({2, 14}), "substitution") in offered
    assert (frozenset({13, 14}), "bench_priority") in offered
    assert not any(kind == "bench_priority" and players & {1, 12} for players, kind in offered)


def test_us6_my_team_view_offers_nothing_for_a_squad_that_is_not_a_legal_fifteen() -> None:
    result = GetMyTeamViewService(
        _FakeCurrentSquadRepository(), _FakeProjectionRepository()
    ).execute()

    assert result is not None
    assert result.legal_rearrangements == ()
