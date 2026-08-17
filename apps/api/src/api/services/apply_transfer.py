from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.transfers import TransferPlayer, evaluate_single_transfer

from api.repositories.current_squad_repository import (
    CurrentSquadPlayerSave,
    CurrentSquadRecord,
)
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.services.get_my_team_view import MyTeamViewRecord

DEFAULT_MODEL_VERSION = "component_v3"


@dataclass(frozen=True)
class ApplyTransferFailure:
    """An explicit, structured failure -- an illegal or stale transfer is
    always rejected here, never silently applied."""

    code: str
    message: str
    missing_player_ids: tuple[int, ...] = ()
    errors: tuple[str, ...] = ()


class CurrentSquadRepositoryPort(Protocol):
    def get_current(self) -> CurrentSquadRecord | None: ...

    def save_current(
        self,
        *,
        bank: float,
        free_transfers: int,
        players: list[CurrentSquadPlayerSave],
    ) -> CurrentSquadRecord: ...


class ProjectionRunRepositoryPort(Protocol):
    def get_latest(self, model_version: str) -> ProjectionRunRecord | None: ...


class TransferProjectionRepositoryPort(Protocol):
    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]: ...


class TransferPlayerRepositoryPort(Protocol):
    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None: ...


class MyTeamViewServicePort(Protocol):
    def execute(self) -> MyTeamViewRecord | None: ...


class ApplyTransferService:
    def __init__(
        self,
        current_squad_repository: CurrentSquadRepositoryPort,
        projection_run_repository: ProjectionRunRepositoryPort,
        projection_repository: TransferProjectionRepositoryPort,
        player_repository: TransferPlayerRepositoryPort,
        my_team_view_service: MyTeamViewServicePort,
    ) -> None:
        self._current_squad_repository = current_squad_repository
        self._projection_run_repository = projection_run_repository
        self._projection_repository = projection_repository
        self._player_repository = player_repository
        self._my_team_view_service = my_team_view_service

    def execute(
        self, player_out_id: int, player_in_id: int
    ) -> MyTeamViewRecord | ApplyTransferFailure | None:
        current_squad = self._current_squad_repository.get_current()
        if current_squad is None:
            return None

        outgoing = next(
            (player for player in current_squad.players if player.player_id == player_out_id),
            None,
        )
        if outgoing is None:
            return ApplyTransferFailure(
                code="player_not_in_squad",
                message=f"Player {player_out_id} is not in the current squad",
            )

        incoming_profile = self._player_repository.get_by_id(player_in_id)
        if incoming_profile is None:
            return ApplyTransferFailure(
                code="player_not_found",
                message=f"No player exists with id {player_in_id}",
            )

        run = self._projection_run_repository.get_latest(DEFAULT_MODEL_VERSION)
        if run is None:
            return ApplyTransferFailure(
                code="no_projection_run",
                message=f"No projection run found for model_version={DEFAULT_MODEL_VERSION!r}",
            )

        squad_player_ids = [player.player_id for player in current_squad.players]
        all_player_ids = sorted(set(squad_player_ids) | {player_in_id})
        rows = self._projection_repository.list_player_fixture_projections_for_run(
            all_player_ids, run.id
        )
        if not rows:
            return ApplyTransferFailure(
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
            return ApplyTransferFailure(
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

        if not evaluation.is_legal:
            return ApplyTransferFailure(
                code="transfer_illegal",
                message=f"This transfer is not legal: {', '.join(evaluation.errors)}",
                errors=evaluation.errors,
            )

        # The incoming player takes over the outgoing player's exact slot
        # (starting/bench, captain/vice) -- nothing else about the squad
        # changes.
        updated_players = [
            CurrentSquadPlayerSave(
                player_id=player_in_id if player.player_id == player_out_id else player.player_id,
                is_starting=player.is_starting,
                bench_order=player.bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
            )
            for player in current_squad.players
        ]

        self._current_squad_repository.save_current(
            bank=evaluation.resulting_bank,
            free_transfers=current_squad.free_transfers,
            players=updated_players,
        )

        return self._my_team_view_service.execute()
