from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.optimisation import LineupSelection
from fpl_engine.transfers import TransferPlayer, evaluate_single_transfer

from api.repositories.current_squad_repository import CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.candidate_pool_failures import incoming_pool_exclusion, pool_exclusion_message

DEFAULT_MODEL_VERSION = "component_v3"


@dataclass(frozen=True)
class LineupSummary:
    starting_xi: tuple[int, ...]
    bench_goalkeeper: int
    bench_outfield: tuple[int, int, int]
    captain: int
    vice_captain: int
    starting_xi_points: float
    captain_adjusted_points: float


def _summarize(selection: LineupSelection | None) -> LineupSummary | None:
    if selection is None:
        return None
    return LineupSummary(
        starting_xi=selection.starting_xi,
        bench_goalkeeper=selection.bench_goalkeeper,
        bench_outfield=selection.bench_outfield,
        captain=selection.captain,
        vice_captain=selection.vice_captain,
        starting_xi_points=selection.starting_xi_points,
        captain_adjusted_points=selection.captain_adjusted_points,
    )


@dataclass(frozen=True)
class TransferPreviewResult:
    """Preview only -- never persisted. See GetApplyTransferService for the
    explicit, separate action that actually saves a squad change."""

    model_version: str
    projection_run_id: int
    generated_at: dt.datetime
    target_gameweek_number: int
    bank: float
    resulting_bank: float
    selling_price_is_approximate: bool
    player_out_id: int
    player_in_id: int
    is_legal: bool
    errors: tuple[str, ...]
    projected_team_gain: float
    direct_player_xpts_difference: float
    lineup_before: LineupSummary | None
    lineup_after: LineupSummary | None
    captain_changed: bool
    vice_captain_changed: bool


@dataclass(frozen=True)
class TransferPreviewFailure:
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
    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None: ...


class GetTransferPreviewService:
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
        self, player_out_id: int, player_in_id: int
    ) -> TransferPreviewResult | TransferPreviewFailure | None:
        current_squad = self._current_squad_repository.get_current()
        if current_squad is None:
            return None

        outgoing = next(
            (player for player in current_squad.players if player.player_id == player_out_id),
            None,
        )
        if outgoing is None:
            return TransferPreviewFailure(
                code="player_not_in_squad",
                message=f"Player {player_out_id} is not in the current squad",
            )

        incoming_profile = self._player_repository.get_by_id(player_in_id)
        if incoming_profile is None:
            return TransferPreviewFailure(
                code="player_not_found",
                message=f"No player exists with id {player_in_id}",
            )

        exclusion = incoming_pool_exclusion(current_squad.players, player_out_id, incoming_profile)
        if exclusion is not None:
            return TransferPreviewFailure(
                code="player_not_in_candidate_pool",
                message=pool_exclusion_message(exclusion, incoming_profile),
            )

        run = self._projection_run_repository.get_latest(DEFAULT_MODEL_VERSION)
        if run is None:
            return TransferPreviewFailure(
                code="no_projection_run",
                message=f"No projection run found for model_version={DEFAULT_MODEL_VERSION!r}",
            )

        squad_player_ids = [player.player_id for player in current_squad.players]
        all_player_ids = sorted(set(squad_player_ids) | {player_in_id})
        rows = self._projection_repository.list_player_fixture_projections_for_run(
            all_player_ids, run.id
        )
        if not rows:
            return TransferPreviewFailure(
                code="missing_projections",
                message=f"No {DEFAULT_MODEL_VERSION} projections found in run {run.id}",
            )

        target_gameweek_number = min(row.gameweek_number for row in rows)
        points_by_player: dict[int, float] = {}
        for row in rows:
            if row.gameweek_number != target_gameweek_number:
                continue
            points_by_player[row.player_id] = (
                points_by_player.get(row.player_id, 0.0) + row.projected_points
            )

        missing_player_ids = tuple(
            sorted(
                player_id
                for player_id in [*squad_player_ids, player_in_id]
                if player_id not in points_by_player
            )
        )
        if missing_player_ids:
            return TransferPreviewFailure(
                code="missing_projections",
                message=(
                    f"{len(missing_player_ids)} player(s) have no {DEFAULT_MODEL_VERSION} "
                    f"projection for gameweek {target_gameweek_number} in run {run.id}"
                ),
                missing_player_ids=missing_player_ids,
            )

        squad_transfer_players = [
            TransferPlayer(
                player_id=player.player_id,
                position=PlayerPosition(player.position),
                team_id=player.team_id,
                price=player.current_price,
                projected_points=points_by_player[player.player_id],
            )
            for player in current_squad.players
        ]
        incoming_transfer_player = TransferPlayer(
            player_id=incoming_profile.player_id,
            position=PlayerPosition(incoming_profile.position),
            team_id=incoming_profile.team_id,
            price=incoming_profile.current_price,
            projected_points=points_by_player[incoming_profile.player_id],
        )

        evaluation = evaluate_single_transfer(
            squad=squad_transfer_players,
            player_out_id=player_out_id,
            player_in=incoming_transfer_player,
            bank=current_squad.bank,
        )

        lineup_before = _summarize(evaluation.optimal_xi_before)
        lineup_after = _summarize(evaluation.optimal_xi_after)
        captain_changed = (
            lineup_before is not None
            and lineup_after is not None
            and lineup_before.captain != lineup_after.captain
        )
        vice_captain_changed = (
            lineup_before is not None
            and lineup_after is not None
            and lineup_before.vice_captain != lineup_after.vice_captain
        )

        return TransferPreviewResult(
            model_version=DEFAULT_MODEL_VERSION,
            projection_run_id=run.id,
            generated_at=run.generated_at,
            target_gameweek_number=target_gameweek_number,
            bank=current_squad.bank,
            resulting_bank=evaluation.resulting_bank,
            selling_price_is_approximate=True,
            player_out_id=player_out_id,
            player_in_id=player_in_id,
            is_legal=evaluation.is_legal,
            errors=evaluation.errors,
            projected_team_gain=evaluation.projected_team_gain,
            direct_player_xpts_difference=evaluation.direct_player_xpts_difference,
            lineup_before=lineup_before,
            lineup_after=lineup_after,
            captain_changed=captain_changed,
            vice_captain_changed=vice_captain_changed,
        )
