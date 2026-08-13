from pydantic import BaseModel, ConfigDict, Field


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str
    difficulty: int


class TeamListResponse(BaseModel):
    items: list[TeamResponse]
    total: int


class UpdateTeamDifficultyPayload(BaseModel):
    difficulty: int = Field(ge=1, le=5)
