from pydantic import BaseModel, ConfigDict, Field


class CurrentSquadPlayerSelectionRequest(BaseModel):
    player_id: int = Field(ge=1)
    is_starting: bool
    bench_order: int | None = Field(default=None, ge=1, le=4)
    is_captain: bool = False
    is_vice_captain: bool = False


class UpsertCurrentSquadRequestBody(BaseModel):
    bank: float = Field(ge=0)
    free_transfers: int = Field(ge=0, le=5)
    players: list[CurrentSquadPlayerSelectionRequest] = Field(min_length=15, max_length=15)


class CurrentSquadPlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: int
    web_name: str
    first_name: str
    second_name: str
    team_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


class CurrentSquadResponse(BaseModel):
    squad_id: int
    name: str
    bank: float
    free_transfers: int
    players: list[CurrentSquadPlayerResponse]
