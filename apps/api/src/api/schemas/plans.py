from typing import Annotated, Literal
from uuid import UUID

from api.schemas.lineup import LineupRearrangementResponse
from fpl_engine.planning.models import Diagnostic, LineupRole, PurchaseProvenance
from fpl_engine.rules import Chip
from fpl_engine.rules.chips import ChipAvailability
from pydantic import BaseModel, ConfigDict, Field

WireUUID = Annotated[UUID, Field(strict=False)]
WireChip = Annotated[Chip, Field(strict=False)]


class PlannerIntentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RenamePlanIntent(PlannerIntentBody):
    kind: Literal["rename_plan"]
    name: str = Field(min_length=1, max_length=100)


class ChangeHorizonIntent(PlannerIntentBody):
    kind: Literal["change_horizon"]
    start_gameweek: int = Field(ge=1, le=38)
    end_gameweek: int = Field(ge=1, le=38)
    used_chips: list[WireChip] | None = None
    free_hit_gameweek_19: bool | None = None


class StartingTransfersIntent(PlannerIntentBody):
    kind: Literal["set_starting_transfers"]
    value: int | None = Field(ge=0, le=5)


class StartingChipsIntent(PlannerIntentBody):
    kind: Literal["set_starting_chips"]
    used_chips: list[WireChip]
    free_hit_gameweek_19: bool = False


class CorrectPurchaseIntent(PlannerIntentBody):
    kind: Literal["correct_purchase_price"]
    ownership_id: WireUUID
    price_tenths: int = Field(gt=0)


class ConfirmPurchaseIntent(PlannerIntentBody):
    kind: Literal["confirm_purchase_price"]
    ownership_id: WireUUID


class CaptainIntent(PlannerIntentBody):
    kind: Literal["change_captain", "change_vice_captain"]
    gameweek_number: int = Field(ge=1, le=38)
    player_id: int = Field(gt=0)


class SwapIntent(PlannerIntentBody):
    kind: Literal["swap_lineup_players"]
    gameweek_number: int = Field(ge=1, le=38)
    first_player_id: int = Field(gt=0)
    second_player_id: int = Field(gt=0)


class ChipIntent(PlannerIntentBody):
    kind: Literal["activate_chip", "remove_chip"]
    gameweek_number: int = Field(ge=1, le=38)
    chip: WireChip
    expected_chip: WireChip | None = None


class MoveChipIntent(PlannerIntentBody):
    kind: Literal["move_chip"]
    source_gameweek: int = Field(ge=1, le=38)
    target_gameweek: int = Field(ge=1, le=38)
    chip: WireChip


class AddTransferIntent(PlannerIntentBody):
    kind: Literal["add_transfer"]
    gameweek_number: int = Field(ge=1, le=38)
    outgoing_player_id: int = Field(gt=0)
    outgoing_ownership_id: WireUUID
    incoming_player_id: int = Field(gt=0)


class EditTransferIntent(PlannerIntentBody):
    kind: Literal["edit_transfer"]
    decision_id: WireUUID
    outgoing_player_id: int | None = Field(default=None, gt=0)
    outgoing_ownership_id: WireUUID | None = None
    outgoing_source_decision_id: WireUUID | None = None
    incoming_player_id: int | None = Field(default=None, gt=0)


class RemoveTransferIntent(PlannerIntentBody):
    kind: Literal["remove_transfer"]
    decision_id: WireUUID


PlannerIntent = Annotated[
    RenamePlanIntent
    | ChangeHorizonIntent
    | StartingTransfersIntent
    | StartingChipsIntent
    | CorrectPurchaseIntent
    | ConfirmPurchaseIntent
    | CaptainIntent
    | SwapIntent
    | ChipIntent
    | MoveChipIntent
    | AddTransferIntent
    | EditTransferIntent
    | RemoveTransferIntent,
    Field(discriminator="kind"),
]


class PlanMutationRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mutation_id: WireUUID
    expected_revision: int = Field(ge=0)
    intents: list[PlannerIntent] = Field(min_length=1)


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
    slot_id: UUID | None = None
    ownership_id: UUID | None = None
    source_decision_id: UUID | None = None
    purchase_price_tenths: int | None = None
    provenance: dict[str, object] | None = None


class PlanTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: int
    web_name: str


class StartingOwnershipResponse(BaseModel):
    slot_id: UUID
    ownership_id: UUID
    player_id: int = Field(gt=0)
    web_name: str
    purchase_price_tenths: int = Field(gt=0)
    provenance: PurchaseProvenance


class StartingStateResponse(BaseModel):
    players: list[StartingOwnershipResponse] = Field(min_length=15, max_length=15)
    lineup: list[LineupRole] = Field(min_length=15, max_length=15)
    bank_tenths: int
    free_transfers: int | None = Field(ge=0, le=5)
    used_chips: list[Chip]
    free_hit_gameweek_19: bool
    origin: Literal[
        "my_team_capture",
        "legacy_first_gameweek_assumed",
        "rebased_plan",
        "earlier_horizon_assumed",
    ]
    bank_assumptions: list[UUID]


class TransferDecisionResponse(BaseModel):
    decision_id: UUID
    outgoing_player_id: int = Field(gt=0)
    outgoing_ownership_id: UUID
    incoming_player_id: int = Field(gt=0)
    incoming_ownership_id: UUID
    outgoing_market_tenths: int = Field(gt=0)
    incoming_price_tenths: int = Field(gt=0)
    observation_source: str
    observed_at: str
    origin: str
    selling_price_tenths: int | None = Field(default=None, gt=0)
    purchase_price_tenths: int | None = Field(default=None, gt=0)
    basis_kind: Literal["starting", "planned_acquisition"] | None = None
    basis_confirmation: Literal["assumed", "user_confirmed", "authoritative"] | None = None
    outgoing_live_market_tenths: int | None = Field(default=None, gt=0)
    incoming_live_price_tenths: int | None = Field(default=None, gt=0)


class GameweekAccountingResponse(BaseModel):
    starting_bank_tenths: int | None
    closing_bank_tenths: int | None
    free_transfers_available: int | None = Field(ge=0, le=5)
    next_free_transfers: int | None = Field(ge=0, le=5)
    unlimited_transfers: bool
    transfers_made: int | None = Field(ge=0)
    points_hit: int | None = Field(ge=0)


class PlanGameweekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gameweek_number: int
    chip: str | None
    bank: float | None
    free_transfers_available: int | None
    unlimited_transfers: bool
    transfers_made: int | None
    points_hit: int | None
    starting_points: float | None
    bench_points: float | None
    captain_bonus_points: float | None
    total_points: float | None
    players: list[PlanPlayerResponse]
    transfers_in: list[PlanTransferResponse] = Field(default_factory=list)
    transfers_out: list[PlanTransferResponse] = Field(default_factory=list)
    decisions: list[TransferDecisionResponse] = Field(default_factory=list)
    accounting: GameweekAccountingResponse | None = None
    chip_availability: dict[Chip, ChipAvailability] = Field(default_factory=dict)
    legal_rearrangements: list[LineupRearrangementResponse] = Field(default_factory=list)
    evaluation_status: Literal["complete", "blocked"] = "complete"


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    name: str
    start_gameweek: int
    end_gameweek: int
    initial_bank: float
    initial_free_transfers: int
    total_points: float | None
    total_points_hit: int | None
    gameweeks: list[PlanGameweekResponse]
    revision: int = Field(default=0, ge=0)
    evaluator_version: str = "planner-foundations-1"
    foundation_state: Literal["legacy_pending", "ready"] = "legacy_pending"
    starting_state: StartingStateResponse | None = None
    financial_status: dict[str, object] = Field(default_factory=dict)
    decision_errors: list[Diagnostic] = Field(default_factory=list)
    initialization: dict[str, object] = Field(default_factory=dict)


class PlanMutationResponse(BaseModel):
    status: Literal["committed", "already_committed", "accepted_not_saved"]
    mutation_id: UUID
    committed_revision: int | None
    plan: PlanResponse
    candidate: PlanResponse | None = None


class PlannerErrorResponse(BaseModel):
    code: str
    message: str
    mutation_id: UUID | None = None
    plan: PlanResponse | None = None
    candidate: PlanResponse | None = None
    intent_metadata: dict[str, object] | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
