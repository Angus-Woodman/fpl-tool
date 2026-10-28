from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from fpl_engine.rules import RuleViolationError
from fpl_engine.transfers.priced_player import PricedPlayer

IncomingSelectabilityExclusion = Literal["player_not_selectable", "selectability_unknown"]

CandidatePoolExclusion = Literal[
    "player_already_in_squad",
    "different_position",
    "player_not_selectable",
    "selectability_unknown",
]


def incoming_selectability_exclusion(
    can_select: bool | None, can_transact: bool | None
) -> IncomingSelectabilityExclusion | None:
    """Why an incoming player cannot be bought on imported flags alone, else None.

    A known False in either flag wins over a missing other flag; any remaining
    missing flag is unknown (never eligible). Playing status is not an input.
    """
    if can_select is False or can_transact is False:
        return "player_not_selectable"
    if can_select is None or can_transact is None:
        return "selectability_unknown"
    return None


def candidate_pool_exclusion(
    squad: Sequence[PricedPlayer],
    player_out_id: int,
    candidate: PricedPlayer,
) -> CandidatePoolExclusion | None:
    """Return why `candidate` is outside the replacement pool for `player_out_id`,
    or None if it is in the pool.

    Pool membership is distinct from transfer legality (budget, club limit).
    Reasons are reported in precedence order: structural (already owned, then
    wrong position), then known non-selectable (either flag False, even if the
    other is missing), then unknown selectability. Playing status is not an input.
    """
    outgoing = next((player for player in squad if player.player_id == player_out_id), None)
    if outgoing is None:
        raise RuleViolationError(
            "player_not_in_squad", f"Player {player_out_id} is not in the current squad"
        )

    if any(player.player_id == candidate.player_id for player in squad):
        return "player_already_in_squad"
    if candidate.position != outgoing.position:
        return "different_position"
    return incoming_selectability_exclusion(candidate.can_select, candidate.can_transact)
