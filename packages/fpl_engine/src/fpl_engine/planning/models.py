from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules.chips import Chip, season_half
from fpl_engine.rules.errors import RuleViolationError

Confirmation = Literal["assumed", "user_confirmed", "authoritative"]
BoundaryOrigin = Literal[
    "my_team_capture", "legacy_first_gameweek_assumed", "rebased_plan", "earlier_horizon_assumed"
]


def require_integer(value: int, label: str, minimum: int | None = None) -> None:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise RuleViolationError("invalid_integer", f"{label} must be a whole integer >= {minimum}")


def require_uuid(value: UUID) -> None:
    if not isinstance(value, UUID):
        raise RuleViolationError("invalid_identity", "Planner identities must be UUIDs")


@dataclass(frozen=True)
class PlayerRuleData:
    player_id: int
    position: PlayerPosition
    team_id: int


@dataclass(frozen=True)
class PurchaseProvenance:
    source: str
    original_price_tenths: int
    basis_kind: Literal["starting", "planned_acquisition"] = "starting"
    confirmation: Confirmation | None = "assumed"

    def __post_init__(self) -> None:
        require_integer(self.original_price_tenths, "Original purchase price", 1)
        if not self.source or self.basis_kind not in {"starting", "planned_acquisition"}:
            raise RuleViolationError(
                "invalid_provenance", "Purchase source and basis kind required"
            )
        if (self.basis_kind == "planned_acquisition" and self.confirmation is not None) or (
            self.basis_kind == "starting"
            and self.confirmation not in {"assumed", "user_confirmed", "authoritative"}
        ):
            raise RuleViolationError("invalid_provenance", "Confirmation must match the basis kind")


@dataclass(frozen=True)
class Ownership:
    slot_id: UUID
    ownership_id: UUID
    player_id: int
    purchase_price_tenths: int
    provenance: PurchaseProvenance

    def __post_init__(self) -> None:
        require_uuid(self.slot_id)
        require_uuid(self.ownership_id)
        require_integer(self.player_id, "Player ID", 1)
        require_integer(self.purchase_price_tenths, "Purchase price", 1)


@dataclass(frozen=True)
class LineupRole:
    slot_id: UUID
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool

    def __post_init__(self) -> None:
        require_uuid(self.slot_id)
        if any(
            type(value) is not bool
            for value in (self.is_starting, self.is_captain, self.is_vice_captain)
        ):
            raise RuleViolationError("invalid_lineup", "Lineup flags must be boolean")
        if self.bench_order is not None:
            require_integer(self.bench_order, "Bench order", 1)


def validate_lineup_slots(lineup: tuple[LineupRole, ...], slots: frozenset[UUID]) -> None:
    if len(lineup) != 15 or frozenset(role.slot_id for role in lineup) != slots:
        raise RuleViolationError(
            "lineup_slots", "Lineup must reference exactly the 15 stable slots"
        )


@dataclass(frozen=True)
class Boundary:
    players: tuple[Ownership, ...]
    lineup: tuple[LineupRole, ...]
    bank_tenths: int
    free_transfers: int | None
    used_chips: frozenset[Chip] = frozenset()
    free_hit_gameweek_19: bool = False
    origin: BoundaryOrigin = "my_team_capture"
    bank_assumptions: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        if len(self.players) != 15:
            raise RuleViolationError("squad_size", "Boundary must contain exactly 15 players")
        for values in (
            [player.player_id for player in self.players],
            [player.slot_id for player in self.players],
            [player.ownership_id for player in self.players],
        ):
            if len(set(values)) != 15:
                raise RuleViolationError("duplicate_identity", "Boundary identities must be unique")
        validate_lineup_slots(self.lineup, frozenset(player.slot_id for player in self.players))
        require_integer(self.bank_tenths, "Boundary bank")
        if self.free_transfers is not None:
            require_integer(self.free_transfers, "Starting free transfers", 0)
            if self.free_transfers > 5:
                raise RuleViolationError(
                    "starting_transfers", "Starting free transfers must be 0..5"
                )
        if not all(isinstance(chip, Chip) for chip in self.used_chips):
            raise RuleViolationError("invalid_chip", "Unknown starting chip")
        if type(self.free_hit_gameweek_19) is not bool:
            raise RuleViolationError("invalid_declaration", "FH19 declaration must be boolean")


@dataclass(frozen=True)
class TransferDecision:
    decision_id: UUID
    outgoing_player_id: int
    outgoing_ownership_id: UUID
    incoming_player_id: int
    incoming_ownership_id: UUID
    outgoing_market_tenths: int
    incoming_price_tenths: int
    observation_source: str
    observed_at: str
    origin: Literal["captured", "legacy_initialized_estimate"]

    def __post_init__(self) -> None:
        for identifier in (
            self.decision_id,
            self.outgoing_ownership_id,
            self.incoming_ownership_id,
        ):
            require_uuid(identifier)
        for player_id in (self.outgoing_player_id, self.incoming_player_id):
            require_integer(player_id, "Player ID", 1)
        require_integer(self.outgoing_market_tenths, "Saved outgoing market", 1)
        require_integer(self.incoming_price_tenths, "Saved incoming price", 1)
        if self.outgoing_player_id == self.incoming_player_id:
            raise RuleViolationError("same_player_transfer", "A transfer must change the player")
        if self.outgoing_ownership_id == self.incoming_ownership_id:
            raise RuleViolationError(
                "duplicate_identity", "Acquisition needs a new ownership identity"
            )
        if not self.observation_source or not self.observed_at:
            raise RuleViolationError("missing_observation", "Saved price observation is required")


@dataclass(frozen=True)
class GameweekDecision:
    gameweek_number: int
    lineup: tuple[LineupRole, ...]
    transfers: tuple[TransferDecision, ...] = ()
    chip: Chip | None = None

    def __post_init__(self) -> None:
        require_integer(self.gameweek_number, "Gameweek", 1)
        season_half(self.gameweek_number)
        outgoing = [transfer.outgoing_player_id for transfer in self.transfers]
        incoming = [transfer.incoming_player_id for transfer in self.transfers]
        identifiers = [transfer.decision_id for transfer in self.transfers]
        if (
            len(set(outgoing)) != len(outgoing)
            or len(set(incoming)) != len(incoming)
            or (len(set(identifiers)) != len(identifiers))
        ):
            raise RuleViolationError(
                "duplicate_transfer", "Net transfers must have unique identities"
            )
        if set(outgoing) & set(incoming):
            raise RuleViolationError(
                "same_gameweek_round_trip", "Same-gameweek round trips unsupported"
            )
        if self.chip is not None and not isinstance(self.chip, Chip):
            raise RuleViolationError("invalid_chip", "Unknown planned chip")


@dataclass(frozen=True)
class Plan:
    name: str
    start_gameweek: int
    end_gameweek: int
    boundary: Boundary
    gameweeks: tuple[GameweekDecision, ...]
    revision: int = 0

    def __post_init__(self) -> None:
        require_integer(self.start_gameweek, "Start gameweek", 1)
        require_integer(self.end_gameweek, "End gameweek", 1)
        season_half(self.start_gameweek)
        season_half(self.end_gameweek)
        require_integer(self.revision, "Revision", 0)
        numbers = tuple(gameweek.gameweek_number for gameweek in self.gameweeks)
        if self.start_gameweek > self.end_gameweek or numbers != tuple(
            range(self.start_gameweek, self.end_gameweek + 1)
        ):
            raise RuleViolationError(
                "plan_horizon", "Plan gameweeks must match its ordered horizon"
            )
        slots = frozenset(player.slot_id for player in self.boundary.players)
        decision_ids: set[UUID] = set()
        ownership_ids = {player.ownership_id for player in self.boundary.players}
        for gameweek in self.gameweeks:
            validate_lineup_slots(gameweek.lineup, slots)
            for transfer in gameweek.transfers:
                if (
                    transfer.decision_id in decision_ids
                    or transfer.incoming_ownership_id in ownership_ids
                ):
                    raise RuleViolationError(
                        "duplicate_identity", "Decision/acquisition IDs must be unique"
                    )
                decision_ids.add(transfer.decision_id)
                ownership_ids.add(transfer.incoming_ownership_id)


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    gameweek_number: int
    decision_id: UUID | None = None
    conflicting_gameweek: int | None = None
    player_id: int | None = None


@dataclass(frozen=True)
class DecisionSale:
    decision_id: UUID
    selling_price_tenths: int
    purchase_price_tenths: int | None = None
    basis_kind: Literal["starting", "planned_acquisition"] | None = None
    basis_confirmation: Confirmation | None = None


@dataclass(frozen=True)
class EvaluatedGameweek:
    gameweek_number: int
    players: tuple[Ownership, ...] | None
    lineup: tuple[LineupRole, ...]
    starting_bank_tenths: int | None
    closing_bank_tenths: int | None
    free_transfers_available: int | None
    next_free_transfers: int | None
    unlimited_transfers: bool
    transfers_made: int | None
    points_hit: int | None
    permanent_players: tuple[Ownership, ...] | None
    permanent_bank_tenths: int | None
    provisional_dependencies: frozenset[UUID]
    financial_issue_gameweeks: frozenset[int]
    sales: tuple[DecisionSale, ...] = ()
    permanent_bank_dependencies: frozenset[UUID] = frozenset()

    @property
    def shortfall_tenths(self) -> int | None:
        return None if self.closing_bank_tenths is None else max(0, -self.closing_bank_tenths)


@dataclass(frozen=True)
class PlanEvaluation:
    gameweeks: tuple[EvaluatedGameweek, ...]
    diagnostics: tuple[Diagnostic, ...]

    @property
    def earliest_shortfall_gameweek(self) -> int | None:
        return next(
            (week.gameweek_number for week in self.gameweeks if week.shortfall_tenths), None
        )


@dataclass(frozen=True)
class RenamePlan:
    name: str


@dataclass(frozen=True)
class SetStartingTransfers:
    value: int | None


@dataclass(frozen=True)
class SetStartingChips:
    used_chips: frozenset[Chip]
    free_hit_gameweek_19: bool = False


@dataclass(frozen=True)
class CorrectPurchasePrice:
    ownership_id: UUID
    price_tenths: int


@dataclass(frozen=True)
class ConfirmPurchasePrice:
    ownership_id: UUID


@dataclass(frozen=True)
class ChangeCaptain:
    gameweek_number: int
    player_id: int


@dataclass(frozen=True)
class ChangeViceCaptain:
    gameweek_number: int
    player_id: int


@dataclass(frozen=True)
class SwapLineupPlayers:
    gameweek_number: int
    first_player_id: int
    second_player_id: int


@dataclass(frozen=True)
class SetChip:
    gameweek_number: int
    chip: Chip | None
    expected_chip: Chip | None


@dataclass(frozen=True)
class MoveChip:
    source_gameweek: int
    target_gameweek: int
    chip: Chip


@dataclass(frozen=True)
class AddTransfer:
    gameweek_number: int
    decision: TransferDecision


@dataclass(frozen=True)
class EditTransfer:
    decision_id: UUID
    decision: TransferDecision


@dataclass(frozen=True)
class RemoveTransfer:
    decision_id: UUID


@dataclass(frozen=True)
class ChangeHorizon:
    start_gameweek: int
    end_gameweek: int
    used_chips: frozenset[Chip] | None = None
    free_hit_gameweek_19: bool | None = None


Intent = (
    RenamePlan
    | SetStartingTransfers
    | SetStartingChips
    | CorrectPurchasePrice
    | ConfirmPurchasePrice
    | ChangeCaptain
    | ChangeViceCaptain
    | SwapLineupPlayers
    | SetChip
    | MoveChip
    | AddTransfer
    | EditTransfer
    | RemoveTransfer
    | ChangeHorizon
)
