from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from fpl_engine.domain import PlayerPosition
from fpl_engine.optimisation import LineupCandidate, optimise_lineup

from api.repositories.current_squad_repository import CurrentSquadRecord
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.projection_run_repository import ProjectionRunRecord

DEFAULT_MODEL_VERSION = "component_v3"


@dataclass(frozen=True)
class MyTeamRecommendation:
    """Advice only -- never persisted merely because it was computed. See
    fpl_engine.optimisation.LineupSelection, which this maps field-for-field;
    the formation search, bench ordering, captain/vice choice, and
    tie-breaking all happen there, not in this service."""

    model_version: str
    projection_run_id: int
    generated_at: dt.datetime
    target_gameweek_number: int
    starting_xi_points: float
    captain_adjusted_points: float
    starting_xi: tuple[int, ...]
    bench_goalkeeper: int
    bench_outfield: tuple[int, int, int]
    captain: int
    vice_captain: int
    # Each squad player's own projection for the target gameweek, so the
    # caller can render "Captain Haaland: 3.45 xPts" style cues without
    # recalculating anything.
    player_projected_points: dict[int, float]


@dataclass(frozen=True)
class MyTeamRecommendationFailure:
    """An explicit, structured failure -- never a silent fallback to another
    model, an older run, or stale projections."""

    code: str
    message: str
    missing_player_ids: tuple[int, ...] = ()


class CurrentSquadRepositoryPort(Protocol):
    def get_current(self) -> CurrentSquadRecord | None: ...


class ProjectionRunRepositoryPort(Protocol):
    def get_latest(self, model_version: str) -> ProjectionRunRecord | None: ...


class MyTeamProjectionRepositoryPort(Protocol):
    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]: ...


class GetMyTeamRecommendationService:
    def __init__(
        self,
        current_squad_repository: CurrentSquadRepositoryPort,
        projection_run_repository: ProjectionRunRepositoryPort,
        projection_repository: MyTeamProjectionRepositoryPort,
    ) -> None:
        self._current_squad_repository = current_squad_repository
        self._projection_run_repository = projection_run_repository
        self._projection_repository = projection_repository

    def execute(
        self, model_version: str = DEFAULT_MODEL_VERSION
    ) -> MyTeamRecommendation | MyTeamRecommendationFailure | None:
        current_squad = self._current_squad_repository.get_current()
        if current_squad is None:
            return None

        run = self._projection_run_repository.get_latest(model_version)
        if run is None:
            return MyTeamRecommendationFailure(
                code="no_projection_run",
                message=f"No projection run found for model_version={model_version!r}",
            )

        player_ids = [player.player_id for player in current_squad.players]
        rows = self._projection_repository.list_player_fixture_projections_for_run(
            player_ids, run.id
        )

        points_by_player: dict[int, float] = {}
        if rows:
            target_gameweek_number = min(row.gameweek_number for row in rows)
            for row in rows:
                if row.gameweek_number != target_gameweek_number:
                    continue
                points_by_player[row.player_id] = (
                    points_by_player.get(row.player_id, 0.0) + row.projected_points
                )
        else:
            target_gameweek_number = 0

        missing_player_ids = tuple(
            sorted(player_id for player_id in player_ids if player_id not in points_by_player)
        )
        if missing_player_ids:
            return MyTeamRecommendationFailure(
                code="missing_player_projections",
                message=(
                    f"{len(missing_player_ids)} squad player(s) have no {model_version} "
                    f"projection in run {run.id}. Never falling back to another model, "
                    "run, or stale data."
                ),
                missing_player_ids=missing_player_ids,
            )

        candidates = [
            LineupCandidate(
                player_id=player.player_id,
                position=PlayerPosition(player.position),
                team_id=player.team_id,
                projected_points=points_by_player[player.player_id],
            )
            for player in current_squad.players
        ]
        selection = optimise_lineup(candidates)

        return MyTeamRecommendation(
            model_version=model_version,
            projection_run_id=run.id,
            generated_at=run.generated_at,
            target_gameweek_number=target_gameweek_number,
            starting_xi_points=selection.starting_xi_points,
            captain_adjusted_points=selection.captain_adjusted_points,
            starting_xi=selection.starting_xi,
            bench_goalkeeper=selection.bench_goalkeeper,
            bench_outfield=selection.bench_outfield,
            captain=selection.captain,
            vice_captain=selection.vice_captain,
            player_projected_points=points_by_player,
        )
