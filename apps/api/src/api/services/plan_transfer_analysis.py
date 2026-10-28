"""Planner-aware Transfer Explorer analysis (read-only).

The service is built only from read ports and analyses an already resolved
`PlanningContext`; it has no plan repository, session or mutation capability, so it can
be exercised without a database. Candidate legality comes from the Planner's own
acceptance rules (`fpl_engine.planning.hypothetical`), best-XI ranking from the shared
`rank_replacement_candidates`, and plan impact from `fpl_engine.planning.impact`.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.evaluate import EVALUATOR_VERSION
from fpl_engine.planning.hypothetical import (
    CandidateAssessment,
    CandidateQuote,
    TransferOperation,
    resolve_transfer_operation,
)
from fpl_engine.planning.hypothetical import assess_candidate as assess
from fpl_engine.planning.impact import HORIZONS, PlanImpact, compute_plan_impact, horizon_window
from fpl_engine.planning.models import EvaluatedGameweek, Ownership, PlayerRuleData
from fpl_engine.planning.prices import selling_price_tenths
from fpl_engine.rules import RuleViolationError, exact_tenths
from fpl_engine.transfers import (
    GameweekProjections,
    PricedPlayer,
    candidate_pool_exclusion,
    rank_replacement_candidates,
)

from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.repositories.team_read_repository import TeamReadItem
from api.services.candidate_pool_failures import selectability_unknown_pool_message
from api.services.plan_context import ContextRef, PlanningContext

DEFAULT_MODEL_VERSION = "component_v3"
PROJECTION_WINDOW = max(HORIZONS)


@dataclass(frozen=True)
class PlanSummary:
    plan_id: int
    name: str
    revision: int
    start_gameweek: int
    end_gameweek: int
    gameweek: int
    chip: str | None
    evaluator_version: str


@dataclass(frozen=True)
class HorizonInfo:
    horizon: int
    requested_gameweeks: list[int]
    evaluated_gameweeks: list[int]
    saved_plan_gameweeks: list[int]
    assumed_gameweeks: list[int]
    partial: bool


@dataclass(frozen=True)
class ProjectionInfo:
    model_version: str
    run_id: int
    generated_at: dt.datetime
    newer_run_available: bool
    primary_horizon: int
    horizons: list[HorizonInfo]
    limited_to_selected_gameweek: bool
    limited_reason: str | None


@dataclass(frozen=True)
class AccountingBefore:
    starting_bank_tenths: int | None
    closing_bank_tenths: int | None
    free_transfers_available: int | None
    transfers_made: int | None
    points_hit: int | None
    unlimited_transfers: bool
    provisional: bool


@dataclass(frozen=True)
class PurchaseBasis:
    basis_kind: str
    confirmation: str | None


@dataclass(frozen=True)
class OutgoingSummary:
    player_id: int
    web_name: str
    position: str
    team_short_name: str
    ownership_id: UUID
    operation: str
    replaces_decision_id: UUID | None
    purchase_price_tenths: int
    purchase_basis: PurchaseBasis
    market_price_tenths: int
    selling_price_tenths: int | None
    selling_provisional: bool
    projected_points_by_horizon: dict[int, float]


@dataclass(frozen=True)
class ConflictInfo:
    kind: str
    gameweek: int
    decision_id: UUID | None
    code: str
    message: str
    shortfall_tenths: int | None


@dataclass(frozen=True)
class PlanImpactInfo:
    saved_plan: float | None
    assumed_continuation: float | None
    net_saved_plan: float | None
    valid_through_gameweek: int | None


@dataclass(frozen=True)
class FixtureInfo:
    gameweek: int
    opponent_short_name: str | None
    is_home: bool | None
    difficulty: int | None


@dataclass(frozen=True)
class PlanCandidate:
    player_id: int
    web_name: str
    team_short_name: str
    position: str
    status: str
    price_tenths: int
    state: str
    reasons: list[str]
    conflict: ConflictInfo | None
    valid_through_gameweek: int | None
    resulting_bank_tenths: int | None
    points_hit_after: int | None
    best_xi_gain_by_horizon: dict[int, float]
    direct_xpts_difference: float | None
    plan_impact_by_horizon: dict[int, PlanImpactInfo]
    fixtures: list[FixtureInfo]


@dataclass(frozen=True)
class PlanTransferList:
    planning_context: ContextRef
    plan: PlanSummary
    projection: ProjectionInfo
    accounting_before: AccountingBefore
    outgoing: OutgoingSummary
    candidates: list[PlanCandidate]


@dataclass(frozen=True)
class PreviewCandidate:
    player_id: int
    web_name: str
    team_short_name: str
    position: str
    status: str
    price_tenths: int


@dataclass(frozen=True)
class AccountingSnapshot:
    closing_bank_tenths: int | None
    free_transfers_available: int | None
    transfers_made: int | None
    points_hit: int | None
    next_free_transfers: int | None


@dataclass(frozen=True)
class PreviewAccounting:
    before: AccountingSnapshot
    after: AccountingSnapshot


@dataclass(frozen=True)
class PointsDelta:
    before: float
    after: float
    delta: float


@dataclass(frozen=True)
class PreviewGameweek:
    gameweek: int
    basis: str
    valid: bool
    chip: str | None
    accounting: PreviewAccounting | None
    squad_changed: bool
    incoming_role: str | None
    points: PointsDelta | None
    reason: str | None


@dataclass(frozen=True)
class PreviewTotals:
    saved_plan: float | None
    assumed_continuation: float | None
    hit_change: int
    net_saved_plan: float | None


@dataclass(frozen=True)
class LineupEffect:
    captain_changed: bool
    vice_captain_changed: bool


@dataclass(frozen=True)
class BestXi:
    gain_by_horizon: dict[int, float]
    direct_xpts_difference: float | None


@dataclass(frozen=True)
class CommitIntent:
    kind: str
    incoming_player_id: int
    gameweek_number: int | None = None
    outgoing_player_id: int | None = None
    outgoing_ownership_id: UUID | None = None
    decision_id: UUID | None = None


@dataclass(frozen=True)
class PriceGuard:
    expected_outgoing_market_tenths: int
    expected_incoming_price_tenths: int


@dataclass(frozen=True)
class CommitDescriptor:
    """A description of the Planner mutation to submit; the Explorer persists nothing."""

    intent: CommitIntent
    guard: PriceGuard
    expected_revision: int


@dataclass(frozen=True)
class PlanTransferPreview:
    planning_context: ContextRef
    plan: PlanSummary
    projection: ProjectionInfo
    accounting_before: AccountingBefore
    outgoing: OutgoingSummary
    candidate: PreviewCandidate
    state: str
    reasons: list[str]
    conflict: ConflictInfo | None
    valid_through_gameweek: int | None
    confirmable: bool
    commit: CommitDescriptor | None
    gameweeks: list[PreviewGameweek]
    totals: dict[int, PreviewTotals]
    lineup_effect: LineupEffect
    best_xi: BestXi


@dataclass(frozen=True)
class PlanTransferFailure:
    code: str
    message: str
    missing_player_ids: tuple[int, ...] = ()


class PlayersPort(Protocol):
    def list_by_position(self, position: str) -> list[CandidatePlayerRecord]: ...

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None: ...


class LookupPort(Protocol):
    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]: ...


class RunsPort(Protocol):
    def get(self, run_id: int) -> ProjectionRunRecord | None: ...

    def get_latest(self, model_version: str) -> ProjectionRunRecord | None: ...


class ProjectionsPort(Protocol):
    def list_player_fixture_projections_for_run(
        self,
        player_ids: list[int],
        run_id: int,
        *,
        min_gameweek: int | None = None,
        max_gameweek: int | None = None,
    ) -> list[PlayerProjectionFixtureRecord]: ...


class TeamsPort(Protocol):
    def list_teams(self) -> list[TeamReadItem]: ...


@dataclass(frozen=True)
class _Prepared:
    context: PlanningContext
    operation: TransferOperation
    run: ProjectionRunRecord
    newer_run_available: bool
    outgoing_record: CandidatePlayerRecord
    squad: tuple[Ownership, ...]
    squad_priced: list[PricedPlayer]
    pool: list[CandidatePlayerRecord]
    metadata: dict[int, PlayerRuleData]
    market_tenths: dict[int, int]
    rows_by_player: dict[int, list[PlayerProjectionFixtureRecord]]
    points: dict[int, dict[int, float]]
    evaluated: list[int]


def _tenths(value: float, label: str) -> int:
    return exact_tenths(value, label=label)


class PlanTransferAnalysisService:
    def __init__(
        self,
        *,
        players: PlayersPort,
        lookup: LookupPort,
        runs: RunsPort,
        projections: ProjectionsPort,
        teams: TeamsPort,
    ) -> None:
        self._players = players
        self._lookup = lookup
        self._runs = runs
        self._projections = projections
        self._teams = teams

    def list_candidates(
        self,
        context: PlanningContext,
        player_out_id: int,
        *,
        primary_horizon: int = 5,
        projection_run_id: int | None = None,
    ) -> PlanTransferList | PlanTransferFailure:
        try:
            prepared = self._prepare(context, player_out_id, projection_run_id)
            if isinstance(prepared, PlanTransferFailure):
                return prepared
            return self._list(prepared, primary_horizon)
        except RuleViolationError as error:
            if error.code != "invalid_money":
                raise
            return PlanTransferFailure(error.code, error.message)

    def preview(
        self,
        context: PlanningContext,
        player_out_id: int,
        player_in_id: int,
        *,
        projection_run_id: int | None = None,
    ) -> PlanTransferPreview | PlanTransferFailure:
        try:
            prepared = self._prepare(context, player_out_id, projection_run_id)
            if isinstance(prepared, PlanTransferFailure):
                return prepared
            record = self._players.get_by_id(player_in_id)
            if record is None:
                return PlanTransferFailure(
                    "player_not_found", f"No player exists with id {player_in_id}"
                )
            if not any(item.player_id == player_in_id for item in prepared.pool):
                return PlanTransferFailure(
                    "player_not_in_candidate_pool",
                    f"{record.web_name} is not in the replacement pool for this player",
                )
            return self._preview(prepared, record)
        except RuleViolationError as error:
            if error.code != "invalid_money":
                raise
            return PlanTransferFailure(error.code, error.message)

    def _preview(self, prepared: _Prepared, record: CandidatePlayerRecord) -> PlanTransferPreview:
        context, operation = prepared.context, prepared.operation
        plan, gameweek = context.plan, context.ref.gameweek
        selected = operation.selected_player_id
        covered = set(prepared.points)
        windows = {h: horizon_window(plan, gameweek, h, covered) for h in HORIZONS}
        ranked = rank_replacement_candidates(
            squad=prepared.squad_priced,
            player_out_id=selected,
            candidates=[_priced(record)],
            bank=0.0,
            gameweek_projections=[
                GameweekProjections(number, prepared.points[number])
                for number in prepared.evaluated
            ],
            horizons=list(HORIZONS),
            primary_horizon=max(HORIZONS),
        )
        gains = dict(ranked[0].team_gain_by_horizon) if ranked else {h: 0.0 for h in HORIZONS}
        price = _tenths(record.current_price, "Player price")
        sold_market = prepared.market_tenths[operation.sold_player_id]
        assessment = assess(
            plan,
            context.baseline,
            prepared.metadata,
            operation,
            CandidateQuote(record.player_id, sold_market, price),
        )
        impact = (
            compute_plan_impact(
                plan=plan,
                baseline=context.baseline,
                candidate=assessment.evaluation,
                metadata=prepared.metadata,
                projections=prepared.points,
                gameweek=gameweek,
                valid_through=assessment.valid_through_gameweek,
            )
            if assessment.evaluation is not None
            else None
        )
        conflict = assessment.conflict
        selected_points = prepared.points[gameweek].get(selected)
        candidate_points = prepared.points[gameweek].get(record.player_id)
        commit = (
            _commit(context, operation, record.player_id, sold_market, price)
            if assessment.confirmable
            else None
        )
        return PlanTransferPreview(
            context.ref,
            _plan_summary(context),
            self._projection_info(prepared, max(HORIZONS), windows),
            _accounting(context),
            _outgoing(prepared, windows),
            PreviewCandidate(
                record.player_id,
                record.web_name,
                record.team_short_name,
                record.position,
                record.status,
                price,
            ),
            assessment.state,
            list(assessment.reasons),
            None
            if conflict is None
            else ConflictInfo(
                conflict.kind,
                conflict.gameweek,
                conflict.decision_id,
                conflict.code,
                conflict.message,
                conflict.shortfall_tenths,
            ),
            assessment.valid_through_gameweek,
            assessment.confirmable,
            commit,
            _preview_gameweeks(prepared, assessment, impact, record.player_id),
            {
                horizon: PreviewTotals(
                    None if impact is None else impact.totals[horizon].saved_plan,
                    None if impact is None else impact.totals[horizon].assumed_continuation,
                    0 if impact is None else impact.totals[horizon].hit_change,
                    None if impact is None else impact.totals[horizon].net_saved_plan,
                )
                for horizon in HORIZONS
            },
            _lineup_effect(context, assessment),
            BestXi(
                gains,
                None
                if candidate_points is None or selected_points is None
                else candidate_points - selected_points,
            ),
        )

    def _prepare(
        self, context: PlanningContext, player_out_id: int, projection_run_id: int | None
    ) -> _Prepared | PlanTransferFailure:
        gameweek = context.ref.gameweek
        try:
            operation = resolve_transfer_operation(
                context.plan, context.baseline, gameweek, player_out_id
            )
        except RuleViolationError as error:
            if error.code != "player_not_in_squad":
                raise
            return PlanTransferFailure(error.code, error.message)

        run_or_failure = self._resolve_run(projection_run_id)
        if isinstance(run_or_failure, PlanTransferFailure):
            return run_or_failure
        run, newer_run_available = run_or_failure

        outgoing_record = self._players.get_by_id(player_out_id)
        if outgoing_record is None:
            return PlanTransferFailure(
                "player_not_found", f"No player exists with id {player_out_id}"
            )
        squad = context.selected_week.players
        assert squad is not None  # the resolver rejects blocked gameweeks
        squad_ids = [player.player_id for player in squad]
        lookup_items = {
            item.player_id: item
            for item in self._lookup.get_by_ids(sorted({*squad_ids, operation.sold_player_id}))
        }
        market_tenths = {
            player_id: _tenths(item.current_price, "Player price")
            for player_id, item in lookup_items.items()
        }
        squad_priced = [
            PricedPlayer(
                player_id=player.player_id,
                position=context.metadata[player.player_id].position,
                team_id=context.metadata[player.player_id].team_id,
                price=lookup_items[player.player_id].current_price,
            )
            for player in squad
        ]
        candidate_pool = self._players.list_by_position(outgoing_record.position)
        exclusions = {
            candidate.player_id: candidate_pool_exclusion(
                squad_priced, player_out_id, _priced(candidate)
            )
            for candidate in candidate_pool
        }
        unknown = sum(1 for reason in exclusions.values() if reason == "selectability_unknown")
        if unknown:
            return PlanTransferFailure(
                "selectability_unknown", selectability_unknown_pool_message(unknown)
            )
        pool = [item for item in candidate_pool if exclusions[item.player_id] is None]

        metadata = dict(context.metadata)
        for item in pool:
            metadata[item.player_id] = PlayerRuleData(
                item.player_id, PlayerPosition(item.position), item.team_id
            )

        window_ids = self._window_player_ids(context)
        last = min(gameweek + PROJECTION_WINDOW - 1, 38)
        rows = self._projections.list_player_fixture_projections_for_run(
            sorted({*window_ids, *(item.player_id for item in pool)}),
            run.id,
            min_gameweek=gameweek,
            max_gameweek=last,
        )
        points: dict[int, dict[int, float]] = defaultdict(dict)
        rows_by_player: dict[int, list[PlayerProjectionFixtureRecord]] = defaultdict(list)
        for row in rows:
            bucket = points[row.gameweek_number]
            bucket[row.player_id] = bucket.get(row.player_id, 0.0) + row.projected_points
            rows_by_player[row.player_id].append(row)
        if gameweek not in points:
            return PlanTransferFailure(
                "gameweek_not_projected",
                f"Run {run.id} has no {DEFAULT_MODEL_VERSION} projections for gameweek {gameweek}",
            )
        evaluated = list(
            horizon_window(context.plan, gameweek, PROJECTION_WINDOW, set(points)).evaluated
        )
        missing = tuple(
            sorted(
                player_id
                for player_id in squad_ids
                if not any(player_id in points[number] for number in evaluated)
            )
        )
        if missing:
            return PlanTransferFailure(
                "missing_projections",
                f"{len(missing)} squad player(s) have no {DEFAULT_MODEL_VERSION} "
                f"projection in run {run.id}",
                missing,
            )
        return _Prepared(
            context,
            operation,
            run,
            newer_run_available,
            outgoing_record,
            squad,
            squad_priced,
            pool,
            metadata,
            market_tenths,
            dict(rows_by_player),
            dict(points),
            evaluated,
        )

    def _resolve_run(
        self, projection_run_id: int | None
    ) -> tuple[ProjectionRunRecord, bool] | PlanTransferFailure:
        latest = self._runs.get_latest(DEFAULT_MODEL_VERSION)
        if projection_run_id is None:
            if latest is None:
                return PlanTransferFailure(
                    "no_projection_run",
                    f"No projection run found for model_version={DEFAULT_MODEL_VERSION!r}",
                )
            return latest, False
        run = self._runs.get(projection_run_id)
        if run is None:
            return PlanTransferFailure(
                "run_not_found", f"Projection run {projection_run_id} not found"
            )
        if run.model_version != DEFAULT_MODEL_VERSION:
            return PlanTransferFailure(
                "run_model_mismatch",
                f"Run {projection_run_id} is {run.model_version}, not {DEFAULT_MODEL_VERSION}",
            )
        return run, latest is not None and latest.id != run.id

    @staticmethod
    def _window_player_ids(context: PlanningContext) -> set[int]:
        identifiers: set[int] = set()
        for week in context.baseline.gameweeks:
            for ownerships in (week.players, week.permanent_players):
                if ownerships is not None:
                    identifiers.update(player.player_id for player in ownerships)
        return identifiers

    def _list(self, prepared: _Prepared, primary_horizon: int) -> PlanTransferList:
        context, operation = prepared.context, prepared.operation
        plan, gameweek = context.plan, context.ref.gameweek
        covered = set(prepared.points)
        windows = {h: horizon_window(plan, gameweek, h, covered) for h in HORIZONS}
        selected = operation.selected_player_id
        gameweek_projections = [
            GameweekProjections(number, prepared.points[number]) for number in prepared.evaluated
        ]
        ranked = rank_replacement_candidates(
            squad=prepared.squad_priced,
            player_out_id=selected,
            candidates=[_priced(item) for item in prepared.pool],
            bank=0.0,
            gameweek_projections=gameweek_projections,
            horizons=list(HORIZONS),
            primary_horizon=primary_horizon,
        )
        records = {item.player_id: item for item in prepared.pool}
        difficulty = {team.short_name: team.difficulty for team in self._teams.list_teams()}
        sold_market = prepared.market_tenths[operation.sold_player_id]
        selected_points = prepared.points[gameweek].get(selected)
        candidates: list[PlanCandidate] = []
        for replacement in ranked:
            record = records[replacement.candidate_player_id]
            assessment = assess(
                plan,
                context.baseline,
                prepared.metadata,
                operation,
                CandidateQuote(
                    record.player_id, sold_market, _tenths(record.current_price, "Player price")
                ),
            )
            impact = (
                compute_plan_impact(
                    plan=plan,
                    baseline=context.baseline,
                    candidate=assessment.evaluation,
                    metadata=prepared.metadata,
                    projections=prepared.points,
                    gameweek=gameweek,
                    valid_through=assessment.valid_through_gameweek,
                )
                if assessment.evaluation is not None
                else None
            )
            candidate_points = prepared.points[gameweek].get(record.player_id)
            candidates.append(
                _candidate(
                    record,
                    assessment,
                    impact,
                    dict(replacement.team_gain_by_horizon),
                    None
                    if candidate_points is None or selected_points is None
                    else candidate_points - selected_points,
                    _fixtures(prepared, record.player_id, difficulty),
                )
            )
        return PlanTransferList(
            context.ref,
            _plan_summary(context),
            self._projection_info(prepared, primary_horizon, windows),
            _accounting(context),
            _outgoing(prepared, windows),
            candidates,
        )

    @staticmethod
    def _projection_info(
        prepared: _Prepared, primary_horizon: int, windows: Mapping[int, object]
    ) -> ProjectionInfo:
        horizons = []
        limited = None
        for horizon in HORIZONS:
            window = horizon_window(
                prepared.context.plan, prepared.context.ref.gameweek, horizon, set(prepared.points)
            )
            limited = window.limited_reason
            horizons.append(
                HorizonInfo(
                    horizon,
                    list(window.requested),
                    list(window.evaluated),
                    list(window.saved_plan),
                    list(window.assumed),
                    window.partial,
                )
            )
        return ProjectionInfo(
            DEFAULT_MODEL_VERSION,
            prepared.run.id,
            prepared.run.generated_at,
            prepared.newer_run_available,
            primary_horizon,
            horizons,
            limited is not None,
            limited,
        )


def _priced(record: CandidatePlayerRecord) -> PricedPlayer:
    return PricedPlayer(
        player_id=record.player_id,
        position=PlayerPosition(record.position),
        team_id=record.team_id,
        price=record.current_price,
        can_select=record.can_select,
        can_transact=record.can_transact,
    )


def _plan_summary(context: PlanningContext) -> PlanSummary:
    week = next(
        item for item in context.plan.gameweeks if item.gameweek_number == context.ref.gameweek
    )
    return PlanSummary(
        context.ref.plan_id,
        context.plan.name,
        context.plan.revision,
        context.plan.start_gameweek,
        context.plan.end_gameweek,
        context.ref.gameweek,
        week.chip.value if week.chip is not None else None,
        EVALUATOR_VERSION,
    )


def _accounting(context: PlanningContext) -> AccountingBefore:
    week = context.selected_week
    return AccountingBefore(
        week.starting_bank_tenths,
        week.closing_bank_tenths,
        week.free_transfers_available,
        week.transfers_made,
        week.points_hit,
        week.unlimited_transfers,
        bool(week.provisional_dependencies),
    )


def _outgoing(prepared: _Prepared, windows: Mapping[int, object]) -> OutgoingSummary:
    operation = prepared.operation
    selected = operation.selected_player_id
    ownership = next(item for item in prepared.squad if item.player_id == selected)
    market = prepared.market_tenths[selected]
    is_add = operation.kind == "add_transfer"
    record = prepared.outgoing_record
    horizon_points = {}
    for horizon in HORIZONS:
        window = horizon_window(
            prepared.context.plan, prepared.context.ref.gameweek, horizon, set(prepared.points)
        )
        horizon_points[horizon] = sum(
            prepared.points[number].get(selected, 0.0) for number in window.evaluated
        )
    return OutgoingSummary(
        selected,
        record.web_name,
        record.position,
        record.team_short_name,
        ownership.ownership_id,
        operation.kind,
        operation.replaces_decision_id,
        ownership.purchase_price_tenths,
        PurchaseBasis(ownership.provenance.basis_kind, ownership.provenance.confirmation),
        market,
        selling_price_tenths(ownership.purchase_price_tenths, market) if is_add else None,
        is_add and ownership.provenance.confirmation == "assumed",
        horizon_points,
    )


def _candidate(
    record: CandidatePlayerRecord,
    assessment: CandidateAssessment,
    impact: PlanImpact | None,
    gains: dict[int, float],
    direct_difference: float | None,
    fixtures: list[FixtureInfo],
) -> PlanCandidate:
    conflict = assessment.conflict
    return PlanCandidate(
        record.player_id,
        record.web_name,
        record.team_short_name,
        record.position,
        record.status,
        _tenths(record.current_price, "Player price"),
        assessment.state,
        list(assessment.reasons),
        None
        if conflict is None
        else ConflictInfo(
            conflict.kind,
            conflict.gameweek,
            conflict.decision_id,
            conflict.code,
            conflict.message,
            conflict.shortfall_tenths,
        ),
        assessment.valid_through_gameweek,
        assessment.resulting_bank_tenths,
        assessment.points_hit_after,
        gains,
        direct_difference,
        {
            horizon: PlanImpactInfo(
                None if impact is None else impact.totals[horizon].saved_plan,
                None if impact is None else impact.totals[horizon].assumed_continuation,
                None if impact is None else impact.totals[horizon].net_saved_plan,
                assessment.valid_through_gameweek,
            )
            for horizon in HORIZONS
        },
        fixtures,
    )


def _fixtures(
    prepared: _Prepared, player_id: int, difficulty: Mapping[str, int]
) -> list[FixtureInfo]:
    by_gameweek: dict[int, list[PlayerProjectionFixtureRecord]] = defaultdict(list)
    for row in prepared.rows_by_player.get(player_id, []):
        by_gameweek[row.gameweek_number].append(row)
    fixtures: list[FixtureInfo] = []
    for number in prepared.evaluated:
        rows = by_gameweek.get(number)
        if not rows:
            fixtures.append(FixtureInfo(number, None, None, None))
            continue
        for row in rows:
            opponent = row.opponent_team_short_name
            fixtures.append(
                FixtureInfo(
                    number,
                    opponent,
                    row.is_home,
                    difficulty.get(opponent) if opponent is not None else None,
                )
            )
    return fixtures


def _commit(
    context: PlanningContext,
    operation: TransferOperation,
    incoming_player_id: int,
    sold_market_tenths: int,
    incoming_price_tenths: int,
) -> CommitDescriptor:
    intent = (
        CommitIntent(
            "add_transfer",
            incoming_player_id,
            gameweek_number=context.ref.gameweek,
            outgoing_player_id=operation.sold_player_id,
            outgoing_ownership_id=operation.sold_ownership_id,
        )
        if operation.kind == "add_transfer"
        else CommitIntent(
            "edit_transfer", incoming_player_id, decision_id=operation.replaces_decision_id
        )
    )
    return CommitDescriptor(
        intent,
        PriceGuard(sold_market_tenths, incoming_price_tenths),
        context.ref.revision,
    )


def _snapshot(week: EvaluatedGameweek) -> AccountingSnapshot:
    return AccountingSnapshot(
        week.closing_bank_tenths,
        week.free_transfers_available,
        week.transfers_made,
        week.points_hit,
        week.next_free_transfers,
    )


def _role(week: EvaluatedGameweek, player_id: int) -> str | None:
    if week.players is None:
        return None
    ownership = next((item for item in week.players if item.player_id == player_id), None)
    if ownership is None:
        return None
    role = next((item for item in week.lineup if item.slot_id == ownership.slot_id), None)
    if role is None:
        return None
    if role.is_captain:
        return "captain"
    if role.is_vice_captain:
        return "vice_captain"
    return "starting" if role.is_starting else "bench"


def _ids(players: tuple[Ownership, ...] | None) -> frozenset[int] | None:
    return None if players is None else frozenset(item.player_id for item in players)


def _preview_gameweeks(
    prepared: _Prepared,
    assessment: CandidateAssessment,
    impact: PlanImpact | None,
    player_id: int,
) -> list[PreviewGameweek]:
    plan = prepared.context.plan
    baseline = prepared.context.baseline
    candidate = assessment.evaluation
    impacts = {} if impact is None else {item.gameweek: item for item in impact.by_gameweek}
    rows: list[PreviewGameweek] = []
    for number in prepared.evaluated:
        item = impacts.get(number)
        valid = item is not None and item.available
        points = (
            PointsDelta(item.points_before or 0.0, item.points_after or 0.0, item.delta or 0.0)
            if item is not None and item.available
            else None
        )
        reason = None if valid else (item.reason if item is not None else "beyond_valid_range")
        if number > plan.end_gameweek:
            before_final, after_final = (
                baseline.gameweeks[-1],
                None if candidate is None else candidate.gameweeks[-1],
            )
            rows.append(
                PreviewGameweek(
                    number,
                    "assumed_continuation",
                    valid,
                    None,
                    None,
                    after_final is not None
                    and _ids(before_final.permanent_players) != _ids(after_final.permanent_players),
                    None,
                    points,
                    reason,
                )
            )
            continue
        before = next(week for week in baseline.gameweeks if week.gameweek_number == number)
        after = (
            None
            if candidate is None
            else next(week for week in candidate.gameweeks if week.gameweek_number == number)
        )
        in_range = (
            after is not None
            and after.players is not None
            and (
                assessment.valid_through_gameweek is None
                or number <= assessment.valid_through_gameweek
            )
        )
        decided = next(week for week in plan.gameweeks if week.gameweek_number == number)
        rows.append(
            PreviewGameweek(
                number,
                "saved_plan",
                bool(in_range),
                decided.chip.value if decided.chip is not None else None,
                PreviewAccounting(_snapshot(before), _snapshot(after))
                if in_range and after is not None
                else None,
                bool(in_range)
                and after is not None
                and _ids(before.players) != _ids(after.players),
                _role(after, player_id) if in_range and after is not None else None,
                points,
                reason,
            )
        )
    return rows


def _lineup_effect(context: PlanningContext, assessment: CandidateAssessment) -> LineupEffect:
    candidate = assessment.evaluation
    if candidate is None:
        return LineupEffect(False, False)
    gameweek = context.ref.gameweek
    before = context.selected_week
    after = next(week for week in candidate.gameweeks if week.gameweek_number == gameweek)

    def holder(week: EvaluatedGameweek, attribute: str) -> int | None:
        if week.players is None:
            return None
        slots = {role.slot_id for role in week.lineup if getattr(role, attribute)}
        return next((item.player_id for item in week.players if item.slot_id in slots), None)

    return LineupEffect(
        holder(before, "is_captain") != holder(after, "is_captain"),
        holder(before, "is_vice_captain") != holder(after, "is_vice_captain"),
    )
