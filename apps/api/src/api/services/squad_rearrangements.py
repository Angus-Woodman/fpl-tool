from __future__ import annotations

from collections.abc import Sequence

from fpl_engine.domain import PlayerPosition
from fpl_engine.rules import Rearrangement, SquadSlot, legal_rearrangements

from api.repositories.current_squad_repository import CurrentSquadPlayerRecord


def current_squad_rearrangements(
    players: Sequence[CurrentSquadPlayerRecord],
) -> tuple[Rearrangement, ...]:
    """The engine's legal starter/bench exchanges for the saved My Team squad."""
    return legal_rearrangements(
        [
            SquadSlot(
                player_id=player.player_id,
                position=PlayerPosition(player.position),
                team_id=player.team_id,
                is_starting=player.is_starting,
                bench_order=player.bench_order,
                is_captain=player.is_captain,
                is_vice_captain=player.is_vice_captain,
            )
            for player in players
        ]
    )
