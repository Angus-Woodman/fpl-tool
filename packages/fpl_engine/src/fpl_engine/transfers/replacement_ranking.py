from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers.candidate_pool import candidate_pool_exclusion
from fpl_engine.transfers.priced_player import PricedPlayer
from fpl_engine.transfers.single_transfer import TransferPlayer, evaluate_single_transfer


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
    # False means in the pool and fully comparable, but currently unavailable to apply;
    # `errors` holds the evaluate_single_transfer legality codes (empty when legal).
    is_legal: bool
    errors: tuple[str, ...]


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
    """Rank every in-pool same-position replacement for one outgoing squad player
    by projected team-level gain, summed over each requested horizon.

    Pool membership comes from candidate_pool_exclusion (position, ownership,
    selectability). Builds on evaluate_single_transfer: legality (club limit,
    budget) is evaluated once per candidate -- it does not vary by gameweek,
    since only projected_points does -- and a candidate that fails it is kept,
    flagged is_legal=False with its errors, and ranked alongside legal ones.
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
        if candidate_pool_exclusion(squad, player_out_id, candidate) is not None:
            continue

        per_gameweek_gain: list[float] = []
        resulting_bank = bank
        errors: tuple[str, ...] = ()
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
            errors = evaluation.errors
            per_gameweek_gain.append(evaluation.projected_team_gain)
            resulting_bank = evaluation.resulting_bank

        if not per_gameweek_gain:
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
                is_legal=not errors,
                errors=errors,
            )
        )

    results.sort(
        key=lambda result: (
            -result.team_gain_by_horizon[primary_horizon],
            result.candidate_player_id,
        )
    )
    return results
