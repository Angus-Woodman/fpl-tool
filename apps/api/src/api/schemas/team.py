from pydantic import BaseModel, ConfigDict, Field


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str
    difficulty: int
    source_difficulty: int
    difficulty_override: int | None = None


class TeamListResponse(BaseModel):
    items: list[TeamResponse]
    total: int


class UpdateTeamDifficultyPayload(BaseModel):
    """A null difficulty clears the override and restores the imported rating."""

    difficulty: int | None = Field(default=None, ge=1, le=5)
