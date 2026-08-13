from __future__ import annotations

from api.adapters.fpl.mappers import map_event_live_stats
from api.adapters.fpl.schemas import EventLiveDto


def _payload(*elements: dict[str, object]) -> EventLiveDto:
    return EventLiveDto.model_validate({"elements": list(elements)})


def test_maps_a_players_gameweek_return() -> None:
    seeds = map_event_live_stats(
        _payload(
            {
                "id": 101,
                "stats": {
                    "minutes": 90,
                    "total_points": 8,
                    "goals_scored": 1,
                    "assists": 0,
                    "clean_sheets": 0,
                    "goals_conceded": 1,
                    "bonus": 2,
                    "bps": 34,
                    "starts": 1,
                },
            }
        ),
        gameweek_number=1,
    )

    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.player_external_fpl_id == 101
    assert seed.gameweek_number == 1
    assert seed.minutes == 90
    assert seed.total_points == 8
    assert seed.goals_scored == 1
    assert seed.goals_conceded == 1
    assert seed.bonus == 2
    assert seed.bps == 34
    assert seed.started is True


def test_distinguishes_a_substitute_appearance_from_a_start() -> None:
    seeds = map_event_live_stats(
        _payload({"id": 104, "stats": {"minutes": 23, "starts": 0}}),
        gameweek_number=1,
    )

    assert seeds[0].started is False
    assert seeds[0].minutes == 23


def test_returns_nothing_for_an_empty_pre_season_response() -> None:
    assert map_event_live_stats(_payload(), gameweek_number=1) == []


def test_keeps_players_who_did_not_play() -> None:
    seeds = map_event_live_stats(
        _payload({"id": 102, "stats": {"minutes": 0, "total_points": 0}}),
        gameweek_number=3,
    )

    assert len(seeds) == 1
    assert seeds[0].minutes == 0
    assert seeds[0].total_points == 0


def test_defaults_absent_stats_to_zero() -> None:
    seeds = map_event_live_stats(_payload({"id": 103, "stats": {}}), gameweek_number=2)

    seed = seeds[0]
    assert seed.minutes == 0
    assert seed.goals_scored == 0
    assert seed.bps == 0
    assert seed.started is False
