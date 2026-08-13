from __future__ import annotations

import datetime as dt

from api.adapters.fpl.mappers import map_player_snapshots
from api.adapters.fpl.schemas import BootstrapStaticDto

CAPTURED_AT = dt.datetime(2026, 8, 13, 12, 0, tzinfo=dt.UTC)


def _payload(
    element: dict[str, object], *, events: list[dict[str, object]] | None = None
) -> BootstrapStaticDto:
    return BootstrapStaticDto.model_validate(
        {
            "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS"}],
            "elements": [
                {
                    "id": 101,
                    "first_name": "Bukayo",
                    "second_name": "Saka",
                    "web_name": "Saka",
                    "team": 1,
                    "element_type": 3,
                    "now_cost": 105,
                    "status": "a",
                    **element,
                }
            ],
            "events": events
            if events is not None
            else [
                {
                    "id": 1,
                    "name": "Gameweek 1",
                    "deadline_time": "2026-08-21T17:30:00Z",
                    "is_current": False,
                    "is_next": True,
                    "is_finished": False,
                }
            ],
        }
    )


def test_maps_price_and_availability() -> None:
    snapshots = map_player_snapshots(
        _payload({"now_cost": 105, "status": "d", "chance_of_playing_next_round": 75}),
        captured_at=CAPTURED_AT,
    )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.player_external_fpl_id == 101
    assert snapshot.captured_at == CAPTURED_AT
    assert snapshot.price == 10.5
    assert snapshot.status == "d"
    assert snapshot.chance_of_playing_next_round == 75


def test_parses_numeric_strings_from_the_api() -> None:
    snapshots = map_player_snapshots(
        _payload(
            {
                "selected_by_percent": "73.5",
                "points_per_game": "6.8",
                "form": "2.4",
                "expected_goals": "25.50",
                "expected_assists": "2.67",
            }
        ),
        captured_at=CAPTURED_AT,
    )

    snapshot = snapshots[0]
    assert snapshot.ownership_percent == 73.5
    assert snapshot.points_per_game == 6.8
    assert snapshot.form == 2.4
    assert snapshot.expected_goals == 25.5
    assert snapshot.expected_assists == 2.67


def test_maps_reported_totals() -> None:
    snapshots = map_player_snapshots(
        _payload({"minutes": 2953, "total_points": 239, "starts": 34}),
        captured_at=CAPTURED_AT,
    )

    snapshot = snapshots[0]
    assert snapshot.total_minutes == 2953
    assert snapshot.total_points == 239
    assert snapshot.starts == 34


def test_defaults_when_optional_fields_are_absent() -> None:
    snapshots = map_player_snapshots(_payload({}), captured_at=CAPTURED_AT)

    snapshot = snapshots[0]
    assert snapshot.ownership_percent == 0.0
    assert snapshot.transfers_in == 0
    assert snapshot.transfers_out == 0
    assert snapshot.total_minutes == 0
    assert snapshot.total_points == 0
    assert snapshot.chance_of_playing_next_round is None
    assert snapshot.expected_goals is None


def test_tolerates_unparsable_numeric_strings() -> None:
    snapshots = map_player_snapshots(
        _payload({"selected_by_percent": "", "points_per_game": "n/a"}),
        captured_at=CAPTURED_AT,
    )

    snapshot = snapshots[0]
    assert snapshot.ownership_percent == 0.0
    assert snapshot.points_per_game == 0.0


def test_snapshot_is_attributed_to_the_next_gameweek() -> None:
    snapshots = map_player_snapshots(_payload({}), captured_at=CAPTURED_AT)

    assert snapshots[0].gameweek_number == 1


def test_falls_back_to_the_current_gameweek_when_no_next_gameweek_exists() -> None:
    events = [
        {
            "id": 38,
            "name": "Gameweek 38",
            "deadline_time": "2027-05-20T17:30:00Z",
            "is_current": True,
            "is_next": False,
            "is_finished": False,
        }
    ]

    snapshots = map_player_snapshots(_payload({}, events=events), captured_at=CAPTURED_AT)

    assert snapshots[0].gameweek_number == 38


def test_gameweek_is_absent_when_the_season_is_over() -> None:
    events = [
        {
            "id": 38,
            "name": "Gameweek 38",
            "deadline_time": "2027-05-20T17:30:00Z",
            "is_current": False,
            "is_next": False,
            "is_finished": True,
        }
    ]

    snapshots = map_player_snapshots(_payload({}, events=events), captured_at=CAPTURED_AT)

    assert snapshots[0].gameweek_number is None
