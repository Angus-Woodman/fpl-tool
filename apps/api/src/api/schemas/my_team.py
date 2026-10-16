from api.schemas.lineup import LineupRearrangementResponse
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
    projection_totals: "HorizonProjectionTotalsResponse | None" = None
    fixture_projections: list["PlayerFixtureProjectionResponse"] = Field(default_factory=list)


class PlayerFixtureProjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixture_id: int | None
    gameweek_number: int
    projected_points: float
    kickoff_time: str
    opponent_team_short_name: str | None
    is_home: bool | None


class HorizonProjectionTotalsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    horizon_1: float
    horizon_3: float
    horizon_5: float


class CurrentSquadResponse(BaseModel):
    squad_id: int
    name: str
    bank: float
    free_transfers: int
    projection_totals: HorizonProjectionTotalsResponse | None = None
    bench_projection_totals: HorizonProjectionTotalsResponse | None = None
    captain_adjusted_projection_totals: HorizonProjectionTotalsResponse | None = None
    gameweek_numbers: list[int] = Field(default_factory=list)
    legal_rearrangements: list[LineupRearrangementResponse] = Field(default_factory=list)
    players: list[CurrentSquadPlayerResponse]


class MyTeamRecommendationResponse(BaseModel):
    """Advice only: the frontend must render this separately from the saved
    squad's own is_starting/is_captain flags, not merge them."""

    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    projection_run_id: int
    generated_at: str
    target_gameweek_number: int
    starting_xi_points: float
    captain_adjusted_points: float
    starting_xi: list[int]
    bench_goalkeeper: int
    bench_outfield: list[int]
    captain: int
    vice_captain: int
    player_projected_points: dict[int, float]
    current_captain_adjusted_points: float


class MyTeamRecommendationUnavailableResponse(BaseModel):
    code: str
    message: str
    missing_player_ids: list[int] = Field(default_factory=list)
