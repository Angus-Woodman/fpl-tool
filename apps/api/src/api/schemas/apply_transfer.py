from pydantic import BaseModel, Field


class ApplyTransferRequestBody(BaseModel):
    player_in_id: int = Field(ge=1)


class ApplyTransferUnavailableResponse(BaseModel):
    code: str
    message: str
    missing_player_ids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
