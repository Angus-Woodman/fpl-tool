from __future__ import annotations

import datetime as dt

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class FplTeamDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    short_name: str
    strength: int | None = None


class FplElementDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    first_name: str
    second_name: str
    web_name: str
    team: int
    element_type: int
    now_cost: int
    status: str

    # Mutable state captured into player_snapshots. Before a season starts the
    # reported totals still describe the player's previous season.
    selected_by_percent: str | None = None
    transfers_in_event: int = 0
    transfers_out_event: int = 0
    chance_of_playing_next_round: int | None = None
    minutes: int = 0
    total_points: int = 0
    starts: int = 0
    points_per_game: str | None = None
    form: str | None = None
    expected_goals: str | None = None
    expected_assists: str | None = None


class FplEventDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    deadline_time: dt.datetime
    is_current: bool
    is_next: bool
    is_finished: bool = Field(validation_alias=AliasChoices("is_finished", "finished"))


class BootstrapStaticDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    teams: list[FplTeamDto]
    elements: list[FplElementDto]
    events: list[FplEventDto]


class FplFixtureDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    event: int | None
    team_h: int
    team_a: int
    kickoff_time: dt.datetime
    team_h_score: int | None
    team_a_score: int | None
    finished: bool


class FplLiveStatsDto(BaseModel):
    """Gameweek-aggregated actuals for one player.

    TODO: validate against a real /event/{id}/live/ response once GW1 completes.
    The endpoint returns an empty element list before a season starts, so the
    field set below follows the documented shape rather than a captured payload.
    """

    model_config = ConfigDict(extra="ignore")

    minutes: int = 0
    total_points: int = 0
    goals_scored: int = 0
    assists: int = 0
    clean_sheets: int = 0
    goals_conceded: int = 0
    bonus: int = 0
    bps: int = 0


class FplLiveElementDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    stats: FplLiveStatsDto = Field(default_factory=FplLiveStatsDto)


class EventLiveDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    elements: list[FplLiveElementDto] = Field(default_factory=list)
