from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from fpl_engine.domain import PlayerPosition
from fpl_engine.optimisation import LineupCandidate, LineupSelection, optimise_lineup
from fpl_engine.rules import (
    MAX_PLAYERS_PER_TEAM,
    SQUAD_POSITION_COUNTS,
    exact_tenths,
    observed_tenths,
    tenths_to_money,
)


@dataclass(frozen=True)
class TransferPlayer:
    """A squad member or transfer candidate, priced and projected for the
    target gameweek.

    `price` is used for both buying and selling value -- this codebase does
    not yet model FPL's selling-price rule (profit on a price rise is only
    half-credited). Treat `resulting_bank` as an approximation until that is
    implemented; it is deliberately not invented here.
    """

    player_id: int
    position: PlayerPosition
    team_id: int
    price: float
    projected_points: float


@dataclass(frozen=True)
class SingleTransferEvaluation:
    is_legal: bool
    errors: tuple[str, ...]
    squad_before: tuple[int, ...]
    squad_after: tuple[int, ...]
    optimal_xi_before: LineupSelection | None
    optimal_xi_after: LineupSelection | None
    # The primary metric: optimal team xPts after minus before -- never the
    # naive incoming-minus-outgoing difference, since an upgrade that only
    # improves the bench changes nothing about what actually plays.
    projected_team_gain: float
    # Explanatory only: incoming player's own projection minus the outgoing
    # player's, independent of whether either currently starts.
    direct_player_xpts_difference: float
    resulting_bank: float


def _as_candidate(player: TransferPlayer) -> LineupCandidate:
    return LineupCandidate(
        player_id=player.player_id,
        position=player.position,
        team_id=player.team_id,
        projected_points=player.projected_points,
    )


def evaluate_single_transfer(
    *,
    squad: list[TransferPlayer],
    player_out_id: int,
    player_in: TransferPlayer,
    bank: float,
) -> SingleTransferEvaluation:
    """Evaluate one explicit outgoing/incoming swap against an explicit squad.

    Deliberately does not search for replacements (see
    fpl_engine.transfers for ranking over candidates) and does not apply a
    transfer-cost/hit policy -- that depends on free-transfers-available,
    which this primitive does not assume anything about (see
    fpl_engine.rules.transfers.points_hit for that separate concern).
    """
    squad_before_ids = tuple(player.player_id for player in squad)
    squad_by_id = {player.player_id: player for player in squad}

    errors: list[str] = []
    outgoing = squad_by_id.get(player_out_id)
    if outgoing is None:
        errors.append("player_not_in_squad")
    incoming_already_owned = player_in.player_id in squad_by_id
    if incoming_already_owned:
        errors.append("player_already_in_squad")

    if outgoing is None or incoming_already_owned:
        return SingleTransferEvaluation(
            is_legal=False,
            errors=tuple(errors),
            squad_before=squad_before_ids,
            squad_after=squad_before_ids,
            optimal_xi_before=None,
            optimal_xi_after=None,
            projected_team_gain=0.0,
            direct_player_xpts_difference=(
                player_in.projected_points - outgoing.projected_points
                if outgoing is not None
                else 0.0
            ),
            resulting_bank=bank,
        )

    squad_after_members = [player for player in squad if player.player_id != player_out_id] + [
        player_in
    ]
    squad_after_ids = tuple(player.player_id for player in squad_after_members)

    position_composition_valid = Counter(
        player.position for player in squad_after_members
    ) == Counter(SQUAD_POSITION_COUNTS)
    if not position_composition_valid:
        errors.append("invalid_position_composition")

    club_counts = Counter(player.team_id for player in squad_after_members)
    if any(count > MAX_PLAYERS_PER_TEAM for count in club_counts.values()):
        errors.append("club_limit_exceeded")

    resulting_bank_tenths = (
        observed_tenths(bank, label="Bank")
        + exact_tenths(outgoing.price, label="Player price")
        - exact_tenths(player_in.price, label="Player price")
    )
    resulting_bank = tenths_to_money(resulting_bank_tenths)
    if resulting_bank_tenths < 0:
        errors.append("insufficient_bank")

    direct_player_xpts_difference = player_in.projected_points - outgoing.projected_points

    optimal_xi_before: LineupSelection | None = None
    optimal_xi_after: LineupSelection | None = None
    projected_team_gain = 0.0
    if position_composition_valid:
        optimal_xi_before = optimise_lineup([_as_candidate(player) for player in squad])
        optimal_xi_after = optimise_lineup(
            [_as_candidate(player) for player in squad_after_members]
        )
        projected_team_gain = (
            optimal_xi_after.captain_adjusted_points - optimal_xi_before.captain_adjusted_points
        )

    return SingleTransferEvaluation(
        is_legal=not errors,
        errors=tuple(errors),
        squad_before=squad_before_ids,
        squad_after=squad_after_ids,
        optimal_xi_before=optimal_xi_before,
        optimal_xi_after=optimal_xi_after,
        projected_team_gain=projected_team_gain,
        direct_player_xpts_difference=direct_player_xpts_difference,
        resulting_bank=resulting_bank,
    )
