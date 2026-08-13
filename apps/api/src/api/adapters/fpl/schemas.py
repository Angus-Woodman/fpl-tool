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
