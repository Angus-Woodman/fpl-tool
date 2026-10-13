from __future__ import annotations

from dataclasses import dataclass

from fpl_engine.domain import PlayerPosition


@dataclass(frozen=True)
class PricedPlayer:
    """A squad member or transfer-market candidate's static profile:
    position, club and price. Deliberately excludes projected points, which
    vary per gameweek (see GameweekProjections) rather than per player.

    `can_select` / `can_transact` are the upstream incoming-selectability
    flags; `None` means unknown, which is never treated as eligible."""

    player_id: int
    position: PlayerPosition
    team_id: int
    price: float
    can_select: bool | None = None
    can_transact: bool | None = None
