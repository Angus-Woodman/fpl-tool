from pydantic import BaseModel, ConfigDict, Field


class PlanPlayerSelectionRequest(BaseModel):
    player_id: int = Field(ge=1)
    is_starting: bool
    bench_order: int | None = Field(default=None, ge=1, le=4)
    is_captain: bool = False
    is_vice_captain: bool = False


class CreatePlanRequestBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_gameweek: int = Field(ge=1, le=38)
    end_gameweek: int = Field(ge=1, le=38)


class UpdatePlanRequestBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    start_gameweek: int | None = Field(default=None, ge=1, le=38)
    end_gameweek: int | None = Field(default=None, ge=1, le=38)


class SavePlanGameweekRequestBody(BaseModel):
    chip: str | None = None
    players: list[PlanPlayerSelectionRequest] = Field(min_length=15, max_length=15)


class PlanSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int


class PlanListResponse(BaseModel):
    plans: list[PlanSummaryResponse]


class PlanFixtureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixture_id: int | None
    projected_points: float
    kickoff_time: str
    opponent_team_short_name: str | None
    is_home: bool | None


class PlanPlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: int
    web_name: str
    team_short_name: str
    position: str
    current_price: float
    status: str
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool
    projected_points: float
    fixtures: list[PlanFixtureResponse] = Field(default_factory=list)


class PlanTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: int
    web_name: str


class PlanGameweekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gameweek_number: int
    chip: str | None
    bank: float
    free_transfers_available: int
    unlimited_transfers: bool
    transfers_made: int
    points_hit: int
    starting_points: float
    bench_points: float
    captain_bonus_points: float
    total_points: float
    players: list[PlanPlayerResponse]
    transfers_in: list[PlanTransferResponse] = Field(default_factory=list)
    transfers_out: list[PlanTransferResponse] = Field(default_factory=list)


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int
    initial_bank: float
    initial_free_transfers: int
    total_points: float
    total_points_hit: int
    gameweeks: list[PlanGameweekResponse]
