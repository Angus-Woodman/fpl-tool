from pydantic import BaseModel, ConfigDict


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str


class TeamListResponse(BaseModel):
    items: list[TeamResponse]
    total: int
