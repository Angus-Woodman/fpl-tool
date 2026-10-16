from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers import GameweekProjections, PricedPlayer, rank_replacement_candidates

from api.repositories.current_squad_repository import CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.candidate_pool_failures import (
    incoming_pool_exclusion,
    selectability_unknown_pool_message,
)

DEFAULT_MODEL_VERSION = "component_v3"
HORIZONS = (1, 3, 5)


@dataclass(frozen=True)
class OutgoingPlayerSummary:
    player_id: int
    web_name: str
    position: str
    team_short_name: str
    current_price: float
    # Equal to current_price for now -- see selling_price_is_approximate on
    # TransferExplorerResult. There is no purchase-price data anywhere in
    # this codebase yet, so FPL's real half-profit selling rule cannot be
    # computed.
    selling_price: float
    projected_points_by_horizon: dict[int, float]


@dataclass(frozen=True)
class RankedTransferCandidate:
    player_id: int
    web_name: str
    team_short_name: str
    price: float
    resulting_bank: float
    team_gain_by_horizon: dict[int, float]
    # Incoming minus outgoing raw projection for the nearest evaluated
    # gameweek only -- explanatory, never the ranking metric.
    direct_xpts_difference: float | None
    gameweeks_evaluated: int
    # False means in the pool and fully comparable but currently unavailable to apply.
    is_legal: bool
    # evaluate_single_transfer legality codes; empty when is_legal.
    unavailable_reasons: list[str]
    # Advisory playing status only; never an unavailability reason.
    status: str


@dataclass(frozen=True)
class TransferExplorerResult:
    model_version: str
    projection_run_id: int
    generated_at: dt.datetime
    primary_horizon: int
    bank: float
    selling_price_is_approximate: bool
    outgoing: OutgoingPlayerSummary
    candidates: list[RankedTransferCandidate]
    evaluated_gameweek_numbers: list[int]


@dataclass(frozen=True)
class TransferExplorerFailure:
    """An explicit, structured failure -- never a silent fallback to another
    model, an older run, stale projections, or a broadened candidate pool."""

    code: str
    message: str
    missing_player_ids: tuple[int, ...] = ()


class CurrentSquadRepositoryPort(Protocol):
    def get_current(self) -> CurrentSquadRecord | None: ...


class ProjectionRunRepositoryPort(Protocol):
    def get_latest(self, model_version: str) -> ProjectionRunRecord | None: ...


class TransferProjectionRepositoryPort(Protocol):
    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]: ...


class TransferPlayerRepositoryPort(Protocol):
    def list_by_position(self, position: str) -> list[CandidatePlayerRecord]: ...

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None: ...


class GetTransferExplorerService:
    def __init__(
        self,
        current_squad_repository: CurrentSquadRepositoryPort,
        projection_run_repository: ProjectionRunRepositoryPort,
        projection_repository: TransferProjectionRepositoryPort,
        player_repository: TransferPlayerRepositoryPort,
    ) -> None:
        self._current_squad_repository = current_squad_repository
        self._projection_run_repository = projection_run_repository
        self._projection_repository = projection_repository
        self._player_repository = player_repository

    def execute(
        self, player_out_id: int, primary_horizon: int = 5
    ) -> TransferExplorerResult | TransferExplorerFailure | None:
        current_squad = self._current_squad_repository.get_current()
        if current_squad is None:
            return None

        outgoing_squad_player = next(
            (player for player in current_squad.players if player.player_id == player_out_id),
            None,
        )
        if outgoing_squad_player is None:
            player_exists = self._player_repository.get_by_id(player_out_id) is not None
            if player_exists:
                return TransferExplorerFailure(
                    code="player_not_in_squad",
                    message=f"Player {player_out_id} is not in the current squad",
                )
            return TransferExplorerFailure(
                code="player_not_found",
                message=f"No player exists with id {player_out_id}",
            )

        run = self._projection_run_repository.get_latest(DEFAULT_MODEL_VERSION)
        if run is None:
            return TransferExplorerFailure(
                code="no_projection_run",
                message=f"No projection run found for model_version={DEFAULT_MODEL_VERSION!r}",
            )

        all_candidates = self._player_repository.list_by_position(outgoing_squad_player.position)
        exclusions = {
            candidate.player_id: incoming_pool_exclusion(
                current_squad.players, player_out_id, candidate
            )
            for candidate in all_candidates
        }
        # Only profiles that pass the structural and known-non-selectable tiers can be unknown.
        unknown_count = sum(
            1 for reason in exclusions.values() if reason == "selectability_unknown"
        )
        if unknown_count:
            return TransferExplorerFailure(
                code="selectability_unknown",
                message=selectability_unknown_pool_message(unknown_count),
            )

        candidate_pool = [
            candidate for candidate in all_candidates if exclusions[candidate.player_id] is None
        ]
        candidates_by_id = {candidate.player_id: candidate for candidate in candidate_pool}
        squad_player_ids = [player.player_id for player in current_squad.players]
        all_player_ids = sorted(set(squad_player_ids) | set(candidates_by_id))

        rows = self._projection_repository.list_player_fixture_projections_for_run(
            all_player_ids, run.id
        )
        if not rows:
            return TransferExplorerFailure(
                code="missing_projections",
                message=f"No {DEFAULT_MODEL_VERSION} projections found in run {run.id}",
            )

        points_by_gameweek: dict[int, dict[int, float]] = defaultdict(dict)
        for row in rows:
            bucket = points_by_gameweek[row.gameweek_number]
            bucket[row.player_id] = bucket.get(row.player_id, 0.0) + row.projected_points

        evaluated_gameweek_numbers = sorted(points_by_gameweek)

        missing_squad_player_ids = tuple(
            sorted(
                player_id
                for player_id in squad_player_ids
                if not any(player_id in points_by_gameweek[gw] for gw in evaluated_gameweek_numbers)
            )
        )
        if missing_squad_player_ids:
            return TransferExplorerFailure(
                code="missing_projections",
                message=(
                    f"{len(missing_squad_player_ids)} squad player(s) have no "
                    f"{DEFAULT_MODEL_VERSION} projection in run {run.id}"
                ),
                missing_player_ids=missing_squad_player_ids,
            )

        gameweek_projections = [
            GameweekProjections(
                gameweek_number=gw,
                projected_points_by_player=points_by_gameweek[gw],
            )
            for gw in evaluated_gameweek_numbers
        ]

        squad_priced = [
            PricedPlayer(
                player_id=player.player_id,
                position=PlayerPosition(player.position),
                team_id=player.team_id,
                price=player.current_price,
            )
            for player in current_squad.players
        ]
        candidate_priced = [
            PricedPlayer(
                player_id=candidate.player_id,
                position=PlayerPosition(candidate.position),
                team_id=candidate.team_id,
                price=candidate.current_price,
                can_select=candidate.can_select,
                can_transact=candidate.can_transact,
            )
            for candidate in candidate_pool
        ]

        try:
            ranked = rank_replacement_candidates(
                squad=squad_priced,
                player_out_id=player_out_id,
                candidates=candidate_priced,
                bank=current_squad.bank,
                gameweek_projections=gameweek_projections,
                horizons=list(HORIZONS),
                primary_horizon=primary_horizon,
            )
        except RuleViolationError as error:
            if error.code != "invalid_money":
                raise
            return TransferExplorerFailure(code=error.code, message=error.message)

        nearest_gameweek = evaluated_gameweek_numbers[0] if evaluated_gameweek_numbers else None
        outgoing_points_by_gw = [
            points_by_gameweek[gw].get(player_out_id, 0.0) for gw in evaluated_gameweek_numbers
        ]
        outgoing_projected_points_by_horizon = {
            horizon: sum(outgoing_points_by_gw[: min(horizon, len(outgoing_points_by_gw))])
            for horizon in HORIZONS
        }
        outgoing_nearest_points = (
            points_by_gameweek[nearest_gameweek].get(player_out_id)
            if nearest_gameweek is not None
            else None
        )

        ranked_candidates = []
        for replacement in ranked:
            candidate_profile = candidates_by_id[replacement.candidate_player_id]
            candidate_nearest_points = (
                points_by_gameweek[nearest_gameweek].get(replacement.candidate_player_id)
                if nearest_gameweek is not None
                else None
            )
            direct_xpts_difference = (
                candidate_nearest_points - outgoing_nearest_points
                if candidate_nearest_points is not None and outgoing_nearest_points is not None
                else None
            )
            ranked_candidates.append(
                RankedTransferCandidate(
                    player_id=candidate_profile.player_id,
                    web_name=candidate_profile.web_name,
                    team_short_name=candidate_profile.team_short_name,
                    price=replacement.price,
                    resulting_bank=replacement.resulting_bank,
                    team_gain_by_horizon=dict(replacement.team_gain_by_horizon),
                    direct_xpts_difference=direct_xpts_difference,
                    gameweeks_evaluated=replacement.gameweeks_evaluated,
                    is_legal=replacement.is_legal,
                    unavailable_reasons=list(replacement.errors),
                    status=candidate_profile.status,
                )
            )

        return TransferExplorerResult(
            model_version=DEFAULT_MODEL_VERSION,
            projection_run_id=run.id,
            generated_at=run.generated_at,
            primary_horizon=primary_horizon,
            bank=current_squad.bank,
            selling_price_is_approximate=True,
            outgoing=OutgoingPlayerSummary(
                player_id=outgoing_squad_player.player_id,
                web_name=outgoing_squad_player.web_name,
                position=outgoing_squad_player.position,
                team_short_name=outgoing_squad_player.team_short_name,
                current_price=outgoing_squad_player.current_price,
                selling_price=outgoing_squad_player.current_price,
                projected_points_by_horizon=outgoing_projected_points_by_horizon,
            ),
            candidates=ranked_candidates,
            evaluated_gameweek_numbers=evaluated_gameweek_numbers,
        )
