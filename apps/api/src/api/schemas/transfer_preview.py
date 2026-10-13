from pydantic import BaseModel, ConfigDict, Field


class LineupSummaryResponse(BaseModel):
    starting_xi: list[int]
    bench_goalkeeper: int
    bench_outfield: list[int]
    captain: int
    vice_captain: int
    starting_xi_points: float
    captain_adjusted_points: float


class TransferPreviewResponse(BaseModel):
    """Read-only: never persists a squad change. See
    apply-transfer for the explicit, separate action that does."""

    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    projection_run_id: int
    generated_at: str
    target_gameweek_number: int
    bank: float
    resulting_bank: float
    # Equal to current_price for now -- see api.schemas.transfers for why.
    selling_price_is_approximate: bool
    player_out_id: int
    player_in_id: int
    is_legal: bool
    errors: list[str]
    projected_team_gain: float
    direct_player_xpts_difference: float
    lineup_before: LineupSummaryResponse | None
    lineup_after: LineupSummaryResponse | None
    captain_changed: bool
    vice_captain_changed: bool
    # Advisory playing status of the incoming player; never part of `errors` or `is_legal`.
    player_in_status: str


class TransferPreviewUnavailableResponse(BaseModel):
    code: str
    message: str
    missing_player_ids: list[int] = Field(default_factory=list)
