from pydantic import BaseModel, ConfigDict


class PlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    web_name: str
    first_name: str
    second_name: str
    team_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str


class PlayerListResponse(BaseModel):
    items: list[PlayerResponse]
    total: int
    page: int
    page_size: int
