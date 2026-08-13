from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers.single_transfer import TransferPlayer, evaluate_single_transfer


@dataclass(frozen=True)
class PricedPlayer:
    """A squad member or transfer-market candidate's static profile:
    position, club and price. Deliberately excludes projected points, which
    vary per gameweek (see GameweekProjections) rather than per player."""

    player_id: int
    position: PlayerPosition
    team_id: int
    price: float


@dataclass(frozen=True)
class GameweekProjections:
    gameweek_number: int
    projected_points_by_player: Mapping[int, float]


@dataclass(frozen=True)
class RankedReplacement:
    candidate_player_id: int
    price: float
    resulting_bank: float
    # Cumulative projected team gain for each requested horizon, e.g.
    # {1: 0.3, 3: 0.9, 5: 1.4}. A horizon longer than the supplied
    # gameweek_projections is honestly capped at whatever was available --
    # see gameweeks_evaluated.
    team_gain_by_horizon: Mapping[int, float]
    gameweeks_evaluated: int


def _resolve(profile: PricedPlayer, projected_points: float) -> TransferPlayer:
    return TransferPlayer(
        player_id=profile.player_id,
        position=profile.position,
        team_id=profile.team_id,
        price=profile.price,
        projected_points=projected_points,
    )


def rank_replacement_candidates(
    *,
    squad: Sequence[PricedPlayer],
    player_out_id: int,
    candidates: Sequence[PricedPlayer],
    bank: float,
    gameweek_projections: Sequence[GameweekProjections],
    horizons: Sequence[int],
    primary_horizon: int,
) -> list[RankedReplacement]:
    """Rank legal same-position replacements for one outgoing squad player by
    their projected team-level gain, summed over each requested horizon.

    Builds directly on evaluate_single_transfer (Phase 2): legality (same
    position, club limit, budget) is evaluated once per candidate -- it does
    not vary by gameweek, since only projected_points does -- and only legal
    candidates are returned at all ("identify legal replacements" happens
    here, not as a separate pass the caller must do first).
    """
    squad_by_id = {player.player_id: player for player in squad}
    outgoing = squad_by_id.get(player_out_id)
    if outgoing is None:
        raise RuleViolationError(
            "player_not_in_squad", f"Player {player_out_id} is not in the current squad"
        )

    gameweeks_evaluated = min(max(horizons), len(gameweek_projections)) if horizons else 0
    evaluated_gameweeks = gameweek_projections[:gameweeks_evaluated]

    results: list[RankedReplacement] = []
    for candidate in candidates:
        if candidate.position != outgoing.position or candidate.player_id in squad_by_id:
            continue

        per_gameweek_gain: list[float] = []
        resulting_bank = bank
        is_legal = True
        for gameweek in evaluated_gameweeks:
            points_by_player = gameweek.projected_points_by_player
            evaluation = evaluate_single_transfer(
                squad=[
                    _resolve(player, points_by_player.get(player.player_id, 0.0))
                    for player in squad
                ],
                player_out_id=player_out_id,
                player_in=_resolve(candidate, points_by_player.get(candidate.player_id, 0.0)),
                bank=bank,
            )
            if not evaluation.is_legal:
                is_legal = False
                break
            per_gameweek_gain.append(evaluation.projected_team_gain)
            resulting_bank = evaluation.resulting_bank

        if not is_legal or not per_gameweek_gain:
            continue

        team_gain_by_horizon = {
            horizon: sum(per_gameweek_gain[: min(horizon, len(per_gameweek_gain))])
            for horizon in horizons
        }

        results.append(
            RankedReplacement(
                candidate_player_id=candidate.player_id,
                price=candidate.price,
                resulting_bank=resulting_bank,
                team_gain_by_horizon=team_gain_by_horizon,
                gameweeks_evaluated=len(per_gameweek_gain),
            )
        )

    results.sort(
        key=lambda result: (
            -result.team_gain_by_horizon[primary_horizon],
            result.candidate_player_id,
        )
    )
    return results
