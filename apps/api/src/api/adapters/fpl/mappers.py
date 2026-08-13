from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from api.adapters.fpl.schemas import BootstrapStaticDto, EventLiveDto, FplFixtureDto, FplTeamDto
from api.core.exceptions import DataMappingError
from fpl_engine.domain import Gameweek, PlayerPosition, Team


@dataclass(frozen=True)
class PlayerSeed:
    external_fpl_id: int
    first_name: str
    second_name: str
    web_name: str
    team_external_fpl_id: int
    position: PlayerPosition
    current_price: float
    status: str


@dataclass(frozen=True)
class BootstrapStaticMapped:
    teams: list[Team]
    players: list[PlayerSeed]
    gameweeks: list[Gameweek]


@dataclass(frozen=True)
class FixtureSeed:
    external_fpl_id: int
    gameweek_number: int | None
    home_team_external_fpl_id: int
    away_team_external_fpl_id: int
    kickoff_time: dt.datetime
    home_score: int | None
    away_score: int | None
    finished: bool


@dataclass(frozen=True)
class PlayerSnapshotSeed:
    player_external_fpl_id: int
    captured_at: dt.datetime
    gameweek_number: int | None
    price: float
    ownership_percent: float
    transfers_in: int
    transfers_out: int
    status: str
    chance_of_playing_next_round: int | None
    total_minutes: int
    total_points: int
    starts: int
    points_per_game: float
    form: float
    expected_goals: float | None
    expected_assists: float | None
    expected_goals_per_90: float | None
    expected_assists_per_90: float | None
    expected_goals_conceded_per_90: float | None
    goals_conceded_per_90: float | None
    clean_sheets_per_90: float | None
    saves_per_90: float | None
    starts_per_90: float | None
    defensive_contribution_per_90: float | None
    penalties_order: int | None
    direct_freekicks_order: int | None
    corners_order: int | None
    team_join_date: dt.date | None
    ep_next: float | None


@dataclass(frozen=True)
class PlayerGameweekStatSeed:
    player_external_fpl_id: int
    gameweek_number: int
    minutes: int
    total_points: int
    goals_scored: int
    assists: int
    clean_sheets: int
    goals_conceded: int
    bonus: int
    bps: int
    started: bool


_POSITION_MAP: dict[int, PlayerPosition] = {
    1: PlayerPosition.GOALKEEPER,
    2: PlayerPosition.DEFENDER,
    3: PlayerPosition.MIDFIELDER,
    4: PlayerPosition.FORWARD,
}

_DEFAULT_DIFFICULTY = 3
_MIN_DIFFICULTY = 1
_MAX_DIFFICULTY = 5


def _map_team_difficulty(team: FplTeamDto) -> int:
    """Derive a 1-5 opponent rating from FPL's strength fields.

    `strength` is null pre-season, so the populated overall home/away ratings are
    preferred. Their exact venue semantics are unconfirmed, so both raw values are
    stored alongside this average and can be reinterpreted without re-importing.
    """
    venue_strengths = [
        value
        for value in (team.strength_overall_home, team.strength_overall_away)
        if value is not None and value > 0
    ]
    if venue_strengths:
        # Half-up rather than banker's rounding, so a 4/5 split reads as 5.
        raw = math.floor(sum(venue_strengths) / len(venue_strengths) + 0.5)
    elif team.strength is not None and team.strength > 0:
        raw = team.strength
    else:
        return _DEFAULT_DIFFICULTY

    return max(_MIN_DIFFICULTY, min(_MAX_DIFFICULTY, raw))


def map_bootstrap_static(payload: BootstrapStaticDto) -> BootstrapStaticMapped:
    teams = [
        Team(
            id=0,
            external_fpl_id=team.id,
            name=team.name,
            short_name=team.short_name,
            source_difficulty=_map_team_difficulty(team),
            strength_overall_home=team.strength_overall_home,
            strength_overall_away=team.strength_overall_away,
        )
        for team in payload.teams
    ]

    players: list[PlayerSeed] = []
    for element in payload.elements:
        if element.element_type not in _POSITION_MAP:
            raise DataMappingError(
                f"Unsupported element_type {element.element_type} for player {element.id}"
            )

        players.append(
            PlayerSeed(
                external_fpl_id=element.id,
                first_name=element.first_name,
                second_name=element.second_name,
                web_name=element.web_name,
                team_external_fpl_id=element.team,
                position=_POSITION_MAP[element.element_type],
                current_price=element.now_cost / 10.0,
                status=element.status,
            )
        )

    gameweeks = [
        Gameweek(
            id=0,
            number=event.id,
            name=event.name,
            deadline=event.deadline_time,
            is_current=event.is_current,
            is_next=event.is_next,
            is_finished=event.is_finished,
        )
        for event in payload.events
    ]

    return BootstrapStaticMapped(teams=teams, players=players, gameweeks=gameweeks)


def _parse_float(value: str | None) -> float | None:
    """FPL reports several numeric fields as strings, occasionally empty."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _snapshot_gameweek_number(payload: BootstrapStaticDto) -> int | None:
    for event in payload.events:
        if event.is_next:
            return event.id
    for event in payload.events:
        if event.is_current:
            return event.id
    return None


def map_player_snapshots(
    payload: BootstrapStaticDto, *, captured_at: dt.datetime
) -> list[PlayerSnapshotSeed]:
    """Capture the mutable player state that bootstrap-static overwrites in place."""
    gameweek_number = _snapshot_gameweek_number(payload)

    return [
        PlayerSnapshotSeed(
            player_external_fpl_id=element.id,
            captured_at=captured_at,
            gameweek_number=gameweek_number,
            price=element.now_cost / 10.0,
            ownership_percent=_parse_float(element.selected_by_percent) or 0.0,
            transfers_in=element.transfers_in_event,
            transfers_out=element.transfers_out_event,
            status=element.status,
            chance_of_playing_next_round=element.chance_of_playing_next_round,
            total_minutes=element.minutes,
            total_points=element.total_points,
            starts=element.starts,
            points_per_game=_parse_float(element.points_per_game) or 0.0,
            form=_parse_float(element.form) or 0.0,
            expected_goals=_parse_float(element.expected_goals),
            expected_assists=_parse_float(element.expected_assists),
            expected_goals_per_90=element.expected_goals_per_90,
            expected_assists_per_90=element.expected_assists_per_90,
            expected_goals_conceded_per_90=element.expected_goals_conceded_per_90,
            goals_conceded_per_90=element.goals_conceded_per_90,
            clean_sheets_per_90=element.clean_sheets_per_90,
            saves_per_90=element.saves_per_90,
            starts_per_90=element.starts_per_90,
            defensive_contribution_per_90=element.defensive_contribution_per_90,
            penalties_order=element.penalties_order,
            direct_freekicks_order=element.direct_freekicks_order,
            corners_order=element.corners_and_indirect_freekicks_order,
            team_join_date=element.team_join_date,
            ep_next=_parse_float(element.ep_next),
        )
        for element in payload.elements
    ]


def map_event_live_stats(
    payload: EventLiveDto, *, gameweek_number: int
) -> list[PlayerGameweekStatSeed]:
    """Map gameweek-aggregated actuals. Empty before a gameweek has been played."""
    return [
        PlayerGameweekStatSeed(
            player_external_fpl_id=element.id,
            gameweek_number=gameweek_number,
            minutes=element.stats.minutes,
            total_points=element.stats.total_points,
            goals_scored=element.stats.goals_scored,
            assists=element.stats.assists,
            clean_sheets=element.stats.clean_sheets,
            goals_conceded=element.stats.goals_conceded,
            bonus=element.stats.bonus,
            bps=element.stats.bps,
            started=element.stats.starts > 0,
        )
        for element in payload.elements
    ]


def map_fixtures(payload: list[FplFixtureDto]) -> list[FixtureSeed]:
    fixtures: list[FixtureSeed] = []

    for fixture in payload:
        fixtures.append(
            FixtureSeed(
                external_fpl_id=fixture.id,
                gameweek_number=fixture.event,
                home_team_external_fpl_id=fixture.team_h,
                away_team_external_fpl_id=fixture.team_a,
                kickoff_time=fixture.kickoff_time,
                home_score=fixture.team_h_score,
                away_score=fixture.team_a_score,
                finished=fixture.finished,
            )
        )

    return fixtures
