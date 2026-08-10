from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from api.adapters.fpl.schemas import BootstrapStaticDto, FplFixtureDto
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


_POSITION_MAP: dict[int, PlayerPosition] = {
    1: PlayerPosition.GOALKEEPER,
    2: PlayerPosition.DEFENDER,
    3: PlayerPosition.MIDFIELDER,
    4: PlayerPosition.FORWARD,
}


def map_bootstrap_static(payload: BootstrapStaticDto) -> BootstrapStaticMapped:
    teams = [
        Team(
            id=0,
            external_fpl_id=team.id,
            name=team.name,
            short_name=team.short_name,
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
