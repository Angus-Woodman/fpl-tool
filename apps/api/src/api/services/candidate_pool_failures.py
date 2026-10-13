from __future__ import annotations

from collections.abc import Sequence

from fpl_engine.domain import PlayerPosition
from fpl_engine.transfers import CandidatePoolExclusion, PricedPlayer, candidate_pool_exclusion

from api.repositories.current_squad_repository import CurrentSquadPlayerRecord
from api.repositories.player_read_repository import CandidatePlayerRecord

_MESSAGES: dict[CandidatePoolExclusion, str] = {
    "player_already_in_squad": "{name} is already in your squad.",
    "different_position": "{name} plays a different position from the player being replaced.",
    "player_not_selectable": "{name} is not currently selectable in FPL.",
    "selectability_unknown": (
        "Selectability for {name} has not been imported yet. Refresh FPL data and try again."
    ),
}


def incoming_pool_exclusion(
    squad_players: Sequence[CurrentSquadPlayerRecord],
    player_out_id: int,
    incoming: CandidatePlayerRecord,
) -> CandidatePoolExclusion | None:
    """Adapt stored records to the domain profile; the rule itself lives in fpl_engine."""
    squad = [
        PricedPlayer(
            player_id=player.player_id,
            position=PlayerPosition(player.position),
            team_id=player.team_id,
            price=player.current_price,
        )
        for player in squad_players
    ]
    candidate = PricedPlayer(
        player_id=incoming.player_id,
        position=PlayerPosition(incoming.position),
        team_id=incoming.team_id,
        price=incoming.current_price,
        can_select=incoming.can_select,
        can_transact=incoming.can_transact,
    )
    return candidate_pool_exclusion(squad, player_out_id, candidate)


def pool_exclusion_message(reason: CandidatePoolExclusion, incoming: CandidatePlayerRecord) -> str:
    return _MESSAGES[reason].format(name=incoming.web_name)
