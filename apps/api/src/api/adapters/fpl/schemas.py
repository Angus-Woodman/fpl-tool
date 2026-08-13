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
