"""Synthetic full-season dataset for the Planner Explorer performance gate (SC-011).

Builds about 600 players over 20 clubs, one `component_v3` run covering every remaining
gameweek, and an 8-gameweek plan with a Free Hit and later planned transfers. It writes
only through the session it is given, which tests bind to an isolated schema of the
guarded test database.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from api.models import (
    FixtureModel,
    GameweekModel,
    PlayerModel,
    ProjectionModel,
    ProjectionRunModel,
    TeamModel,
)
from api.models.entities import PlayerPosition as StoredPosition
from api.repositories.plan_repository import PlanRepository
from fpl_engine.domain import PlayerPosition
from fpl_engine.planning.evaluate import evaluate_plan
from fpl_engine.planning.models import (
    Boundary,
    GameweekDecision,
    LineupRole,
    Ownership,
    Plan,
    PlayerRuleData,
    PurchaseProvenance,
    TransferDecision,
)
from fpl_engine.rules import Chip
from sqlalchemy import insert
from sqlalchemy.orm import Session

CLUBS = 20
FIRST_GAMEWEEK = 8
LAST_GAMEWEEK = 38
GENERATED_AT = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)
# Per club: 3 goalkeepers, 10 defenders, 12 midfielders, 5 forwards (30 players, 600 in all).
PER_CLUB = (
    (PlayerPosition.GOALKEEPER, 3),
    (PlayerPosition.DEFENDER, 10),
    (PlayerPosition.MIDFIELDER, 12),
    (PlayerPosition.FORWARD, 5),
)
SQUAD_SHAPE = (
    (PlayerPosition.GOALKEEPER, 2),
    (PlayerPosition.DEFENDER, 5),
    (PlayerPosition.MIDFIELDER, 5),
    (PlayerPosition.FORWARD, 3),
)


@dataclass(frozen=True)
class PerfDataset:
    plan_id: int
    plan: Plan
    metadata: dict[int, PlayerRuleData]
    midfielder_in_squad: int


def _identity(number: int) -> UUID:
    return UUID(int=number)


def _price(player_id: int) -> float:
    return round(4.0 + (player_id * 7 % 90) / 10, 1)


def _points(player_id: int, gameweek: int) -> float:
    return round(1.0 + ((player_id * 31 + gameweek * 17) % 70) / 10, 2)


def build_dataset(session: Session) -> PerfDataset:
    teams = [
        TeamModel(
            external_fpl_id=index,
            name=f"Club {index}",
            short_name=f"C{index:02d}",
            source_difficulty=index % 5 + 1,
        )
        for index in range(1, CLUBS + 1)
    ]
    session.add_all(teams)
    session.flush()

    metadata: dict[int, PlayerRuleData] = {}
    club_of_row: dict[int, int] = {}
    number = 0
    for team in teams:
        for position, count in PER_CLUB:
            for _ in range(count):
                number += 1
                metadata[number] = PlayerRuleData(number, position, team.id)
                club_of_row[number] = team.id
    chosen = _choose_squad(metadata)
    rows: list[dict[str, object]] = [
        {
            "id": player_id,
            "external_fpl_id": player_id,
            "first_name": "Player",
            "second_name": str(player_id),
            "web_name": f"P{player_id}",
            "team_id": rule.team_id,
            "position": StoredPosition(rule.position.value),
            "current_price": 5.0 if player_id in chosen else _price(player_id),
            "status": "a",
            "can_select": True,
            "can_transact": True,
        }
        for player_id, rule in metadata.items()
    ]
    session.execute(insert(PlayerModel), rows)

    run = ProjectionRunModel(
        model_version="component_v3",
        generated_at=GENERATED_AT,
        gameweeks_covered=list(range(FIRST_GAMEWEEK, LAST_GAMEWEEK + 1)),
        parameters={},
        team_strength_snapshot={},
        player_snapshot_generated_at=GENERATED_AT,
    )
    session.add(run)
    session.flush()
    projection_rows: list[dict[str, object]] = []
    for gameweek_number in range(FIRST_GAMEWEEK, LAST_GAMEWEEK + 1):
        gameweek = GameweekModel(
            number=gameweek_number,
            name=f"Gameweek {gameweek_number}",
            deadline=dt.datetime(2026, 10, 20, 17, 30, tzinfo=dt.UTC)
            + dt.timedelta(days=gameweek_number),
            is_current=False,
            is_next=gameweek_number == FIRST_GAMEWEEK,
            is_finished=False,
        )
        session.add(gameweek)
        session.flush()
        fixtures = []
        for pair in range(CLUBS // 2):
            fixture = FixtureModel(
                external_fpl_id=gameweek_number * 100 + pair,
                gameweek_id=gameweek.id,
                home_team_id=teams[(pair + gameweek_number) % CLUBS].id,
                away_team_id=teams[(pair + gameweek_number + 10) % CLUBS].id,
                kickoff_time=dt.datetime(2026, 10, 25, 15, 0, tzinfo=dt.UTC)
                + dt.timedelta(days=gameweek_number),
                finished=False,
            )
            session.add(fixture)
            fixtures.append(fixture)
        session.flush()
        fixture_of_team = {}
        for fixture in fixtures:
            fixture_of_team[fixture.home_team_id] = fixture.id
            fixture_of_team[fixture.away_team_id] = fixture.id
        for player_id, rule in metadata.items():
            projection_rows.append(
                {
                    "player_id": player_id,
                    "fixture_id": fixture_of_team[rule.team_id],
                    "gameweek_id": gameweek.id,
                    "projected_points": _points(player_id, gameweek_number),
                    "expected_minutes": 80.0,
                    "generated_at": GENERATED_AT,
                    "model_version": "component_v3",
                    "run_id": run.id,
                }
            )
    session.execute(insert(ProjectionModel), projection_rows)

    plan, in_squad = _build_plan(metadata, chosen)
    repository = PlanRepository(session)
    plan_id = repository.create(
        name=plan.name,
        start_gameweek=plan.start_gameweek,
        end_gameweek=plan.end_gameweek,
        initial_bank=1.0,
        initial_free_transfers=1,
    )
    evaluation = evaluate_plan(plan, metadata)
    assert not evaluation.diagnostics, evaluation.diagnostics
    repository.save_canonical(plan_id, plan, evaluation)
    session.commit()
    return PerfDataset(plan_id, plan, metadata, in_squad)


def _choose_squad(metadata: dict[int, PlayerRuleData]) -> list[int]:
    """A legal 15-player squad using one player from each of 15 different clubs."""
    clubs = sorted({rule.team_id for rule in metadata.values()})
    chosen: list[int] = []
    cursor = 0
    for position, count in SQUAD_SHAPE:
        for _ in range(count):
            club = clubs[cursor]
            cursor += 1
            chosen.append(
                next(
                    player_id
                    for player_id, rule in metadata.items()
                    if rule.team_id == club and rule.position == position
                )
            )
    return sorted(chosen)


def _build_plan(
    metadata: dict[int, PlayerRuleData], chosen: list[int], length: int = 8
) -> tuple[Plan, int]:
    """The chosen squad with a Free Hit and later planned transfers over `length` gameweeks."""
    ownerships = tuple(
        Ownership(
            _identity(index + 1),
            _identity(1000 + index + 1),
            player_id,
            50,
            PurchaseProvenance("stored_player_observation", 50),
        )
        for index, player_id in enumerate(chosen)
    )
    starters = {
        position: [p for p in chosen if metadata[p].position == position]
        for position in (
            PlayerPosition.GOALKEEPER,
            PlayerPosition.DEFENDER,
            PlayerPosition.MIDFIELDER,
            PlayerPosition.FORWARD,
        )
    }
    xi = (
        starters[PlayerPosition.GOALKEEPER][:1]
        + starters[PlayerPosition.DEFENDER][:4]
        + starters[PlayerPosition.MIDFIELDER][:4]
        + starters[PlayerPosition.FORWARD][:2]
    )
    bench = [p for p in chosen if p not in xi]
    lineup = tuple(
        LineupRole(
            _identity(index + 1),
            player_id in xi,
            None if player_id in xi else bench.index(player_id) + 1,
            player_id == xi[5],
            player_id == xi[6],
        )
        for index, player_id in enumerate(chosen)
    )
    boundary = Boundary(ownerships, lineup, 10, 1)

    def swap(number: int, outgoing_index: int, incoming: int) -> TransferDecision:
        outgoing = ownerships[outgoing_index]
        return TransferDecision(
            _identity(2000 + number),
            outgoing.player_id,
            outgoing.ownership_id,
            incoming,
            _identity(3000 + number),
            50,
            50,
            "stored_player_observation",
            "2026-10-14T12:00:00+00:00",
            "captured",
        )

    mids = [
        i
        for i, o in enumerate(ownerships)
        if metadata[o.player_id].position == PlayerPosition.MIDFIELDER
    ]
    free = [
        player_id
        for player_id, rule in metadata.items()
        if rule.position == PlayerPosition.MIDFIELDER
        and rule.team_id not in {metadata[p].team_id for p in chosen}
    ]
    transfers = {
        10: (swap(1, mids[0], free[0]),),
        13: (swap(2, mids[1], free[1]),),
    }
    weeks = tuple(
        GameweekDecision(
            number,
            lineup,
            transfers.get(number, ()),
            Chip.FREE_HIT if number == 11 else None,
        )
        for number in range(FIRST_GAMEWEEK, FIRST_GAMEWEEK + length)
    )
    return (
        Plan("Performance plan", FIRST_GAMEWEEK, FIRST_GAMEWEEK + length - 1, boundary, weeks),
        ownerships[mids[2]].player_id,
    )


def add_long_plan(session: Session, dataset: PerfDataset, length: int) -> int:
    """Another plan on the same squad covering `length` gameweeks (reported, not gating)."""
    plan, _ = _build_plan(dataset.metadata, _choose_squad(dataset.metadata), length)
    repository = PlanRepository(session)
    plan_id = repository.create(
        name=f"Long plan {length}",
        start_gameweek=plan.start_gameweek,
        end_gameweek=plan.end_gameweek,
        initial_bank=1.0,
        initial_free_transfers=1,
    )
    repository.save_canonical(plan_id, plan, evaluate_plan(plan, dataset.metadata))
    session.commit()
    return plan_id
