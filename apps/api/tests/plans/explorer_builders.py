"""API-layer builders for Planner Explorer tests (no database).

Built from the public `fpl_engine` models and the API's own record types. The engine's
test fixtures live in `packages/fpl_engine/tests`; neither layer imports the other's.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID

from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupItem
from api.repositories.team_read_repository import TeamReadItem
from api.services.plan_context import ContextRef, PlanningContext
from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.evaluate import evaluate_plan
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
CLUB_LIMIT_CANDIDATE = 201
SQUAD_MARKET_PRICE = 5.4
DEFAULT_CANDIDATE_PRICE = 5.0
CANDIDATE_PRICES = {107: 5.9, 108: 14.0}
GENERATED_AT = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)
MODEL_VERSION = "component_v3"


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
    return (
        squad
        | pool
        | {CLUB_LIMIT_CANDIDATE: PlayerRuleData(CLUB_LIMIT_CANDIDATE, PlayerPosition.MIDFIELDER, 1)}
    )


def boundary(
    *, bank_tenths: int = 10, free_transfers: int | None = 1, confirmation: Confirmation = "assumed"
) -> Boundary:
    players = tuple(
        Ownership(
            identity(player_id),
            identity(1000 + player_id),
            player_id,
            50,
            PurchaseProvenance("stored_player_observation", 50, "starting", confirmation),
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
    outgoing: int, incoming: int, number: int, *, incoming_price: int = 50, market: int = 54
) -> TransferDecision:
    return TransferDecision(
        identity(2000 + number),
        outgoing,
        identity(1000 + outgoing),
        incoming,
        identity(3000 + number),
        market,
        incoming_price,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )


def plan(
    start: int = 8,
    end: int = 11,
    *,
    chips: Mapping[int, Chip] | None = None,
    transfers: Mapping[int, tuple[TransferDecision, ...]] | None = None,
    base: Boundary | None = None,
) -> Plan:
    starting = base if base is not None else boundary()
    return Plan(
        "Explorer reference plan",
        start,
        end,
        starting,
        tuple(
            GameweekDecision(
                number,
                starting.lineup,
                (transfers or {}).get(number, ()),
                (chips or {}).get(number),
            )
            for number in range(start, end + 1)
        ),
        revision=3,
    )


def context_for(reference: Plan, gameweek: int, *, plan_id: int = 1) -> PlanningContext:
    rules = metadata()
    return PlanningContext(
        ContextRef(plan_id, gameweek, reference.revision),
        reference,
        {player_id: rules[player_id] for player_id in _plan_players(reference)},
        evaluate_plan(reference, rules),
    )


def _plan_players(reference: Plan) -> set[int]:
    identifiers = {player.player_id for player in reference.boundary.players}
    for week in reference.gameweeks:
        for decision in week.transfers:
            identifiers.update((decision.outgoing_player_id, decision.incoming_player_id))
    return identifiers


@dataclass(frozen=True)
class Scenario:
    name: str
    plan: Plan
    gameweek: int


def reference_scenarios() -> tuple[Scenario, ...]:
    """The Planner states the Explorer must handle; each is a complete `Plan`."""
    return (
        Scenario("ordinary", plan(), 8),
        Scenario("first_plan_gameweek", plan(8, 8), 8),
        Scenario("zero_free_transfers", plan(base=boundary(free_transfers=0)), 9),
        Scenario("estimated_basis", plan(base=boundary(confirmation="assumed")), 8),
        Scenario("confirmed_basis", plan(base=boundary(confirmation="user_confirmed")), 8),
        Scenario("wildcard", plan(chips={9: Chip.WILDCARD}), 9),
        Scenario("free_hit", plan(chips={9: Chip.FREE_HIT}), 9),
        Scenario("bench_boost", plan(chips={9: Chip.BENCH_BOOST}), 9),
        Scenario("triple_captain", plan(chips={9: Chip.TRIPLE_CAPTAIN}), 9),
        Scenario(
            "acquired_earlier_in_same_gameweek",
            plan(transfers={9: (transfer(2, 102, 1),)}),
            9,
        ),
        Scenario(
            "existing_shortfall",
            plan(transfers={8: (transfer(4, 104, 5, incoming_price=80),)}),
            9,
        ),
        Scenario(
            "later_sale_of_a_player",
            plan(transfers={10: (transfer(6, 114, 3),)}),
            8,
        ),
        Scenario(
            "later_purchase_of_a_candidate",
            plan(transfers={10: (transfer(7, 107, 4, incoming_price=60),)}),
            8,
        ),
    )


def candidate_records(
    *,
    can_select: bool | None = True,
    can_transact: bool | None = True,
    overrides: Mapping[int, Mapping[str, object]] | None = None,
) -> list[CandidatePlayerRecord]:
    rules = metadata()
    records: list[CandidatePlayerRecord] = []
    for player_id, rule in sorted(rules.items()):
        record = CandidatePlayerRecord(
            player_id=player_id,
            web_name=f"P{player_id}",
            team_id=rule.team_id,
            team_short_name=f"T{rule.team_id}",
            current_price=(
                SQUAD_MARKET_PRICE
                if player_id in SQUAD_IDS
                else CANDIDATE_PRICES.get(player_id, DEFAULT_CANDIDATE_PRICE)
            ),
            position=rule.position.value,
            status="a",
            can_select=can_select,
            can_transact=can_transact,
        )
        records.append(replace(record, **(overrides or {}).get(player_id, {})))  # type: ignore[arg-type]
    return records


class FakePlayers:
    def __init__(self, records: list[CandidatePlayerRecord] | None = None) -> None:
        self.records = records if records is not None else candidate_records()

    def list_by_position(self, position: str) -> list[CandidatePlayerRecord]:
        return [record for record in self.records if record.position == position]

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None:
        return next((record for record in self.records if record.player_id == player_id), None)


class FakeLookup:
    def __init__(self, records: list[CandidatePlayerRecord] | None = None) -> None:
        self._records = records if records is not None else candidate_records()

    def get_by_ids(self, player_ids: list[int]) -> list[SquadPlayerLookupItem]:
        return [
            SquadPlayerLookupItem(
                record.player_id,
                record.team_id,
                record.web_name,
                record.position,
                record.current_price,
                record.can_select,
                record.can_transact,
            )
            for record in self._records
            if record.player_id in player_ids
        ]


class FakeRuns:
    def __init__(self, *runs: ProjectionRunRecord) -> None:
        self.runs = {run.id: run for run in runs}

    def get(self, run_id: int) -> ProjectionRunRecord | None:
        return self.runs.get(run_id)

    def get_latest(self, model_version: str) -> ProjectionRunRecord | None:
        matching = [run for run in self.runs.values() if run.model_version == model_version]
        return max(matching, key=lambda run: (run.generated_at, run.id), default=None)


def run_record(
    run_id: int = 1, *, model_version: str = MODEL_VERSION, hours: int = 0
) -> ProjectionRunRecord:
    return ProjectionRunRecord(
        id=run_id,
        model_version=model_version,
        generated_at=GENERATED_AT + dt.timedelta(hours=hours),
        gameweeks_covered=list(range(1, 39)),
        parameters={},
        team_strength_snapshot={},
        player_snapshot_generated_at=None,
    )


def flat_points(
    gameweeks: range, special: Mapping[int, float] | None = None, *, base: float = 1.0
) -> dict[int, dict[int, float]]:
    special = special or {}
    return {
        gameweek: {player_id: special.get(player_id, base) for player_id in metadata()}
        for gameweek in gameweeks
    }


class FakeProjections:
    """Rows from `points[gameweek][player_id]`; one fixture per player and gameweek."""

    def __init__(self, points: Mapping[int, Mapping[int, float]]) -> None:
        self.points = points
        self.calls: list[tuple[int, int | None, int | None]] = []

    def list_player_fixture_projections_for_run(
        self,
        player_ids: list[int],
        run_id: int,
        *,
        min_gameweek: int | None = None,
        max_gameweek: int | None = None,
    ) -> list[PlayerProjectionFixtureRecord]:
        self.calls.append((run_id, min_gameweek, max_gameweek))
        rows: list[PlayerProjectionFixtureRecord] = []
        for gameweek in sorted(self.points):
            if (min_gameweek is not None and gameweek < min_gameweek) or (
                max_gameweek is not None and gameweek > max_gameweek
            ):
                continue
            for player_id in sorted(set(player_ids) & set(self.points[gameweek])):
                rows.append(
                    PlayerProjectionFixtureRecord(
                        player_id=player_id,
                        fixture_id=gameweek * 1000 + player_id,
                        gameweek_number=gameweek,
                        projected_points=self.points[gameweek][player_id],
                        kickoff_time=f"2026-10-{gameweek:02d}T15:00:00+00:00",
                        opponent_team_short_name=f"O{(gameweek % 5) + 1}",
                        is_home=gameweek % 2 == 0,
                    )
                )
        return rows


class FakeTeams:
    def list_teams(self) -> list[TeamReadItem]:
        return [
            TeamReadItem(
                id=number,
                name=f"Opponent {number}",
                short_name=f"O{number}",
                difficulty=number,
                source_difficulty=number,
                difficulty_override=None,
            )
            for number in range(1, 6)
        ]
