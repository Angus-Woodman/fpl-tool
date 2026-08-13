from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from fpl_engine.rules import (
    Chip,
    SquadDiff,
    diff_squads,
    free_transfers_after,
    points_hit,
)


@dataclass(frozen=True)
class PlanPlayerSelection:
    player_id: int
    is_starting: bool
    bench_order: int | None
    is_captain: bool
    is_vice_captain: bool


@dataclass(frozen=True)
class PlanGameweekState:
    gameweek_number: int
    chip: Chip | None
    players: tuple[PlanPlayerSelection, ...]

    @property
    def player_ids(self) -> frozenset[int]:
        return frozenset(player.player_id for player in self.players)


@dataclass(frozen=True)
class PlanGameweekAccounting:
    gameweek_number: int
    bank: float
    free_transfers_available: int
    transfers_made: int
    points_hit: int
    players_out: tuple[int, ...]
    players_in: tuple[int, ...]


def recalculate_accounting(
    states: Sequence[PlanGameweekState],
    *,
    initial_bank: float,
    initial_free_transfers: int,
    prices: Mapping[int, float],
) -> list[PlanGameweekAccounting]:
    """Roll bank and free transfers forward across a plan.

    A free hit gameweek is a one-week squad, so the following gameweek is
    compared against the last squad that was not played under a free hit.
    """
    results: list[PlanGameweekAccounting] = []
    baseline_ids: frozenset[int] = frozenset()
    baseline_bank = initial_bank
    previous_available = initial_free_transfers
    previous_transfers = 0
    previous_chip: Chip | None = None
    previous_gameweek = states[0].gameweek_number if states else 0

    for index, state in enumerate(states):
        if index == 0:
            available = initial_free_transfers
            diff = SquadDiff(players_out=(), players_in=())
            bank = initial_bank
        else:
            available = free_transfers_after(
                available=previous_available,
                transfers_made=previous_transfers,
                chip=previous_chip,
                gameweek_number=previous_gameweek,
            )
            diff = diff_squads(baseline_ids, state.player_ids)
            bank = (
                baseline_bank
                + sum(prices.get(player_id, 0.0) for player_id in diff.players_out)
                - sum(prices.get(player_id, 0.0) for player_id in diff.players_in)
            )

        hit = points_hit(
            transfers_made=diff.transfer_count,
            free_transfers_available=available,
            chip=state.chip,
            gameweek_number=state.gameweek_number,
        )
        results.append(
            PlanGameweekAccounting(
                gameweek_number=state.gameweek_number,
                bank=round(bank, 1),
                free_transfers_available=available,
                transfers_made=diff.transfer_count,
                points_hit=hit,
                players_out=diff.players_out,
                players_in=diff.players_in,
            )
        )

        previous_available = available
        previous_transfers = diff.transfer_count
        previous_chip = state.chip
        previous_gameweek = state.gameweek_number
        if index == 0 or state.chip is not Chip.FREE_HIT:
            baseline_ids = state.player_ids
            baseline_bank = bank

    return results


def pair_transfers(
    players_out: Sequence[int],
    players_in: Sequence[int],
    positions: Mapping[int, str],
) -> dict[int, int]:
    """Match outgoing players to incoming replacements, preferring same position."""
    remaining_in = list(players_in)
    pairs: dict[int, int] = {}

    for outgoing in players_out:
        match = next(
            (
                incoming
                for incoming in remaining_in
                if positions.get(incoming) == positions.get(outgoing)
            ),
            None,
        )
        if match is None:
            match = remaining_in[0] if remaining_in else None
        if match is None:
            break
        remaining_in.remove(match)
        pairs[outgoing] = match

    return pairs


def apply_transfers_forward(
    states: Sequence[PlanGameweekState],
    *,
    from_index: int,
    pairs: Mapping[int, int],
) -> list[PlanGameweekState]:
    """Carry a gameweek's transfers into later gameweeks that still hold the old player."""
    if not pairs:
        return list(states)

    updated = list(states[: from_index + 1])
    for state in states[from_index + 1 :]:
        current_ids = set(state.player_ids)
        players = list(state.players)
        for index, player in enumerate(players):
            replacement = pairs.get(player.player_id)
            if replacement is None or replacement in current_ids:
                continue
            current_ids.discard(player.player_id)
            current_ids.add(replacement)
            players[index] = replace(player, player_id=replacement)
        updated.append(replace(state, players=tuple(players)))

    return updated
