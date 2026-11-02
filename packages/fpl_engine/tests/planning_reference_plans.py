"""Pure engine fixtures: reference plans for candidate-assessment and plan-impact tests.

Built from `fpl_engine` models only. API tests keep their own equivalents in
`apps/api/tests/plans/explorer_builders.py`; neither layer imports the other.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.models import (
    Boundary,
    Confirmation,
    GameweekDecision,
    LineupRole,
    Ownership,
    Plan,
    PlayerRuleData,
    PurchaseProvenance,
    TransferDecision,
)
from fpl_engine.rules import Chip

SQUAD_POSITIONS = (
    PlayerPosition.GOALKEEPER,
    *([PlayerPosition.DEFENDER] * 4),
    *([PlayerPosition.MIDFIELDER] * 4),
    *([PlayerPosition.FORWARD] * 2),
    PlayerPosition.GOALKEEPER,
    PlayerPosition.DEFENDER,
    PlayerPosition.MIDFIELDER,
    PlayerPosition.FORWARD,
)
SQUAD_IDS = tuple(range(1, 16))
CANDIDATE_OFFSET = 100
# One extra midfielder from club 1, whose three squad places are already taken.
CLUB_LIMIT_CANDIDATE = 201
OUTGOING_MARKET_TENTHS = 54
DEFAULT_PRICE_TENTHS = 50
CANDIDATE_PRICES = {107: 59, 108: 140, 111: 54}


def identity(number: int) -> UUID:
    return UUID(int=number)


def metadata() -> dict[int, PlayerRuleData]:
    squad = {
        index + 1: PlayerRuleData(index + 1, position, index % 5 + 1)
        for index, position in enumerate(SQUAD_POSITIONS)
    }
    pool = {
        player_id + CANDIDATE_OFFSET: PlayerRuleData(
            player_id + CANDIDATE_OFFSET, rule.position, 20 + player_id
        )
        for player_id, rule in squad.items()
    }
    extra = {
        CLUB_LIMIT_CANDIDATE: PlayerRuleData(CLUB_LIMIT_CANDIDATE, PlayerPosition.MIDFIELDER, 1)
    }
    return squad | pool | extra


def candidate_price(player_id: int) -> int:
    return CANDIDATE_PRICES.get(player_id, DEFAULT_PRICE_TENTHS)


def boundary(
    *,
    bank_tenths: int = 10,
    free_transfers: int | None = 1,
    confirmation: Confirmation = "assumed",
) -> Boundary:
    players = tuple(
        Ownership(
            identity(player_id),
            identity(1000 + player_id),
            player_id,
            DEFAULT_PRICE_TENTHS,
            PurchaseProvenance(
                "stored_player_observation", DEFAULT_PRICE_TENTHS, "starting", confirmation
            ),
        )
        for player_id in SQUAD_IDS
    )
    lineup = tuple(
        LineupRole(
            identity(index + 1),
            index < 11,
            None if index < 11 else index - 10,
            index == 1,
            index == 2,
        )
        for index in range(15)
    )
    return Boundary(players, lineup, bank_tenths, free_transfers)


def transfer(
    outgoing: int,
    incoming: int,
    number: int,
    *,
    incoming_price: int = DEFAULT_PRICE_TENTHS,
    outgoing_market: int = OUTGOING_MARKET_TENTHS,
    outgoing_ownership: UUID | None = None,
) -> TransferDecision:
    return TransferDecision(
        identity(2000 + number),
        outgoing,
        outgoing_ownership if outgoing_ownership is not None else identity(1000 + outgoing),
        incoming,
        identity(3000 + number),
        outgoing_market,
        incoming_price,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )


def plan(
    start: int = 8,
    end: int = 11,
    *,
    chips: dict[int, Chip] | None = None,
    transfers: dict[int, tuple[TransferDecision, ...]] | None = None,
    base: Boundary | None = None,
) -> Plan:
    starting = base if base is not None else boundary()
    chips = chips or {}
    transfers = transfers or {}
    return Plan(
        "Reference plan",
        start,
        end,
        starting,
        tuple(
            GameweekDecision(number, starting.lineup, transfers.get(number, ()), chips.get(number))
            for number in range(start, end + 1)
        ),
    )


@dataclass(frozen=True)
class ReferencePlan:
    name: str
    plan: Plan
    gameweeks: tuple[int, ...]


def reference_plans() -> tuple[ReferencePlan, ...]:
    """Plans spanning the Planner states the Explorer must handle (SC-002, SC-003, SC-012)."""
    acquired_earlier = transfer(2, 102, 1)
    acquired_same_week = transfer(3, 103, 2)
    later_sale_of_six = transfer(6, 114, 3)  # sells player 6 in GW10
    later_purchase = transfer(7, 107, 4, incoming_price=60)  # buys candidate 107 in GW10
    existing_shortfall = replace(transfer(4, 104, 5), incoming_price_tenths=80)
    same_gameweek_sale = transfer(7, 109, 6)
    return (
        ReferencePlan("ordinary", plan(), (8, 9, 11)),
        ReferencePlan("first_plan_gameweek", plan(8, 8), (8,)),
        ReferencePlan(
            "starting_gameweek_one", plan(1, 3, base=boundary(free_transfers=None)), (1, 2)
        ),
        ReferencePlan("zero_free_transfers", plan(base=boundary(free_transfers=0)), (8, 9)),
        ReferencePlan("estimated_basis", plan(base=boundary(confirmation="assumed")), (8,)),
        ReferencePlan("confirmed_basis", plan(base=boundary(confirmation="user_confirmed")), (8,)),
        ReferencePlan("wildcard", plan(chips={9: Chip.WILDCARD}), (8, 9, 10)),
        ReferencePlan("free_hit", plan(chips={9: Chip.FREE_HIT}), (8, 9, 10)),
        ReferencePlan("bench_boost", plan(chips={9: Chip.BENCH_BOOST}), (8, 9)),
        ReferencePlan("triple_captain", plan(chips={9: Chip.TRIPLE_CAPTAIN}), (8, 9)),
        ReferencePlan(
            "acquired_earlier_in_same_gameweek",
            plan(transfers={9: (acquired_earlier,)}),
            (8, 9),
        ),
        ReferencePlan(
            "another_transfer_same_gameweek",
            plan(transfers={9: (acquired_same_week,)}),
            (8, 9),
        ),
        ReferencePlan(
            "later_sale_of_a_player",
            plan(transfers={10: (later_sale_of_six,)}),
            (8, 9, 10),
        ),
        ReferencePlan(
            "later_purchase_of_a_candidate",
            plan(transfers={10: (later_purchase,)}),
            (8, 9),
        ),
        ReferencePlan(
            "later_financial_chain",
            plan(
                base=boundary(bank_tenths=10),
                transfers={10: (replace(transfer(3, 103, 7), incoming_price_tenths=60),)},
            ),
            (8, 9),
        ),
        ReferencePlan(
            "existing_shortfall",
            plan(transfers={8: (existing_shortfall,)}),
            (8, 9, 10),
        ),
        ReferencePlan(
            "candidate_sold_same_gameweek",
            plan(transfers={9: (same_gameweek_sale,)}),
            (9,),
        ),
    )
