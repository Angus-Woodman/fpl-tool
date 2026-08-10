from pydantic import BaseModel, ConfigDict


class GameweekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    name: str
    is_current: bool
    is_next: bool
    is_finished: bool


class GameweekListResponse(BaseModel):
    items: list[GameweekResponse]
    total: int
