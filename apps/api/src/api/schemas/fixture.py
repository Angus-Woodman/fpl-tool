from pydantic import BaseModel, ConfigDict


class FixtureTickerItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixture_id: int
    gameweek_number: int | None
    kickoff_time: str
    home_team_short_name: str
    away_team_short_name: str
    finished: bool


class FixtureTickerResponse(BaseModel):
    items: list[FixtureTickerItemResponse]
    total: int
    page: int
    page_size: int
