from pydantic import BaseModel, ConfigDict, Field


class OutgoingPlayerSummaryResponse(BaseModel):
    player_id: int
    web_name: str
    position: str
    team_short_name: str
    current_price: float
    # Equal to current_price for now -- no purchase-price data exists yet to
    # compute FPL's real half-profit selling rule. See
    # TransferExplorerResponse.selling_price_is_approximate.
    selling_price: float
    projected_points_by_horizon: dict[int, float]


class RankedTransferCandidateResponse(BaseModel):
    player_id: int
    web_name: str
    team_short_name: str
    price: float
    resulting_bank: float
    team_gain_by_horizon: dict[int, float]
    direct_xpts_difference: float | None
    gameweeks_evaluated: int
    # False means the candidate is visible, fully comparable, but currently unavailable to apply.
    is_legal: bool
    # The same error codes evaluate_single_transfer produces; empty when is_legal is true.
    unavailable_reasons: list[str]
    # Advisory playing status only; never an unavailability reason or an Apply gate.
    status: str


class TransferExplorerResponse(BaseModel):
    """Read-only: previewing/ranking never persists a squad change."""

    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    projection_run_id: int
    generated_at: str
    primary_horizon: int
    bank: float
    selling_price_is_approximate: bool
    outgoing: OutgoingPlayerSummaryResponse
    candidates: list[RankedTransferCandidateResponse]
    evaluated_gameweek_numbers: list[int]


class TransferExplorerUnavailableResponse(BaseModel):
    code: str
    message: str
    missing_player_ids: list[int] = Field(default_factory=list)
