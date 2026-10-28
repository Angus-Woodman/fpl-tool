"""Response models for the Planner-aware Transfer Explorer (read-only endpoints)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer


class _Response(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ContextRefResponse(_Response):
    plan_id: int
    gameweek: int
    revision: int


class PlanSummaryResponse(_Response):
    plan_id: int
    name: str
    revision: int
    start_gameweek: int
    end_gameweek: int
    gameweek: int
    chip: str | None
    evaluator_version: str


class HorizonInfoResponse(_Response):
    horizon: Literal[1, 3, 5]
    requested_gameweeks: list[int]
    evaluated_gameweeks: list[int]
    saved_plan_gameweeks: list[int]
    assumed_gameweeks: list[int]
    partial: bool


class ProjectionInfoResponse(_Response):
    model_version: str
    run_id: int
    generated_at: dt.datetime
    newer_run_available: bool
    primary_horizon: int
    horizons: list[HorizonInfoResponse]
    limited_to_selected_gameweek: bool
    limited_reason: str | None
    unprojected_candidate_ids: list[int]


class AccountingBeforeResponse(_Response):
    starting_bank_tenths: int | None
    closing_bank_tenths: int | None
    free_transfers_available: int | None
    transfers_made: int | None
    points_hit: int | None
    unlimited_transfers: bool
    provisional: bool


class PurchaseBasisResponse(_Response):
    basis_kind: str
    confirmation: str | None


class OutgoingSummaryResponse(_Response):
    player_id: int
    web_name: str
    position: str
    team_short_name: str
    ownership_id: UUID
    operation: Literal["add_transfer", "edit_transfer"]
    replaces_decision_id: UUID | None
    purchase_price_tenths: int
    purchase_basis: PurchaseBasisResponse
    market_price_tenths: int
    selling_price_tenths: int | None
    selling_provisional: bool
    projected_points_by_horizon: dict[int, float]


class ConflictResponse(_Response):
    kind: Literal["structural", "financial"]
    gameweek: int
    decision_id: UUID | None
    code: str
    message: str
    shortfall_tenths: int | None


class PlanImpactResponse(_Response):
    saved_plan: float | None
    assumed_continuation: float | None
    net_saved_plan: float | None
    valid_through_gameweek: int | None


class FixtureResponse(_Response):
    gameweek: int
    opponent_short_name: str | None
    is_home: bool | None
    difficulty: int | None


class PlanCandidateResponse(_Response):
    player_id: int
    web_name: str
    team_short_name: str
    position: str
    status: str
    price_tenths: int
    state: Literal["available", "unavailable", "blocked_by_later_decision"]
    reasons: list[str]
    conflict: ConflictResponse | None
    valid_through_gameweek: int | None
    resulting_bank_tenths: int | None
    points_hit_after: int | None
    best_xi_gain_by_horizon: dict[int, float]
    direct_xpts_difference: float | None
    plan_impact_by_horizon: dict[int, PlanImpactResponse]
    fixtures: list[FixtureResponse]


class PlanTransferExplorerResponse(_Response):
    """Read-only: listing candidates never writes plan, receipt or My Team data."""

    planning_context: ContextRefResponse
    plan: PlanSummaryResponse
    projection: ProjectionInfoResponse
    accounting_before: AccountingBeforeResponse
    outgoing: OutgoingSummaryResponse
    candidates: list[PlanCandidateResponse]


class PreviewCandidateResponse(_Response):
    player_id: int
    web_name: str
    team_short_name: str
    position: str
    status: str
    price_tenths: int


class AccountingSnapshotResponse(_Response):
    closing_bank_tenths: int | None
    free_transfers_available: int | None
    transfers_made: int | None
    points_hit: int | None
    next_free_transfers: int | None


class PreviewAccountingResponse(_Response):
    before: AccountingSnapshotResponse
    after: AccountingSnapshotResponse


class PointsDeltaResponse(_Response):
    before: float
    after: float
    delta: float


class PreviewGameweekResponse(_Response):
    gameweek: int
    basis: Literal["saved_plan", "assumed_continuation"]
    valid: bool
    chip: str | None
    accounting: PreviewAccountingResponse | None
    squad_changed: bool
    incoming_role: Literal["starting", "bench", "captain", "vice_captain"] | None
    points: PointsDeltaResponse | None
    reason: (
        Literal[
            "no_projection",
            "beyond_valid_range",
            "continuation_lineup_illegal",
            "financial_shortfall",
        ]
        | None
    )
    shortfall_tenths: int | None = None


class PreviewTotalsResponse(_Response):
    saved_plan: float | None
    assumed_continuation: float | None
    hit_change: int
    net_saved_plan: float | None


class LineupEffectResponse(_Response):
    captain_changed: bool
    vice_captain_changed: bool


class BestXiResponse(_Response):
    gain_by_horizon: dict[int, float]
    direct_xpts_difference: float | None


class CommitIntentResponse(_Response):
    kind: Literal["add_transfer", "edit_transfer"]
    incoming_player_id: int
    gameweek_number: int | None = None
    outgoing_player_id: int | None = None
    outgoing_ownership_id: UUID | None = None
    decision_id: UUID | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        # The browser submits this object as a Planner intent, which forbids unknown or null keys.
        data: dict[str, Any] = handler(self)
        return {key: value for key, value in data.items() if value is not None}


class PriceGuardResponse(_Response):
    expected_outgoing_market_tenths: int
    expected_incoming_price_tenths: int


class CommitDescriptorResponse(_Response):
    """The Planner mutation to submit to the Planner's own writer, pinned to a revision."""

    intent: CommitIntentResponse
    guard: PriceGuardResponse
    expected_revision: int


class PlanTransferPreviewResponse(_Response):
    """Read-only: previewing never writes plan, receipt or My Team data."""

    planning_context: ContextRefResponse
    plan: PlanSummaryResponse
    projection: ProjectionInfoResponse
    accounting_before: AccountingBeforeResponse
    outgoing: OutgoingSummaryResponse
    candidate: PreviewCandidateResponse
    state: Literal["available", "unavailable", "blocked_by_later_decision"]
    reasons: list[str]
    conflict: ConflictResponse | None
    valid_through_gameweek: int | None
    confirmable: bool
    commit: CommitDescriptorResponse | None
    gameweeks: list[PreviewGameweekResponse]
    totals: dict[int, PreviewTotalsResponse]
    lineup_effect: LineupEffectResponse
    best_xi: BestXiResponse


class PlanTransferErrorDetail(BaseModel):
    code: str
    message: str
    missing_player_ids: list[int] = Field(default_factory=list)
