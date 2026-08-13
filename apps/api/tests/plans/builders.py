from __future__ import annotations

from dataclasses import replace

from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.services.plan_accounting import PlanPlayerSelection

STARTING_IDS = (1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 14)
BENCH_ORDER = {2: 1, 7: 2, 12: 3, 15: 4}

POSITIONS: dict[int, str] = {
    1: "GK",
    2: "GK",
    3: "DEF",
    4: "DEF",
    5: "DEF",
    6: "DEF",
    7: "DEF",
    8: "MID",
    9: "MID",
    10: "MID",
    11: "MID",
    12: "MID",
    13: "FWD",
    14: "FWD",
    15: "FWD",
    16: "MID",
    17: "MID",
    18: "FWD",
    19: "DEF",
    20: "MID",
    21: "MID",
}

# Transfers are budget-neutral apart from the one expensive option used to
# exercise the budget rule.
PRICES: dict[int, float] = {player_id: 5.0 for player_id in POSITIONS}
PRICES[21] = 9.0


def build_squad() -> list[PlanPlayerSelection]:
    return [
        PlanPlayerSelection(
            player_id=player_id,
            is_starting=player_id in STARTING_IDS,
            bench_order=BENCH_ORDER.get(player_id),
            is_captain=player_id == 13,
            is_vice_captain=player_id == 9,
        )
        for player_id in range(1, 16)
    ]


def transfer(
    players: list[PlanPlayerSelection], *, out_id: int, in_id: int
) -> list[PlanPlayerSelection]:
    return [
        replace(player, player_id=in_id) if player.player_id == out_id else player
        for player in players
    ]


def lookup_items() -> list[SquadPlayerLookupItem]:
    return [
        SquadPlayerLookupItem(
            player_id=player_id,
            team_id=player_id,
            web_name=f"P{player_id}",
            position=position,
            current_price=PRICES[player_id],
        )
        for player_id, position in POSITIONS.items()
    ]


class FakePlayerLookupRepository:
    def __init__(self) -> None:
        self._items = {item.player_id: item for item in lookup_items()}

    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]:
        return [self._items[player_id] for player_id in player_ids if player_id in self._items]
