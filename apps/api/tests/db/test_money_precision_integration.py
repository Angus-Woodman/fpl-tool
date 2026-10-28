from __future__ import annotations

import datetime as dt
from decimal import Decimal
from itertools import pairwise

import pytest
from api.models.entities import PlayerModel, SquadModel
from api.repositories.current_squad_repository import CurrentSquadPlayerSave, CurrentSquadRepository
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.player_read_repository import CandidatePlayerRecord
from api.repositories.projection_run_repository import ProjectionRunRecord
from api.repositories.squad_player_lookup_repository import SquadPlayerLookupRepository
from api.services.apply_transfer import ApplyTransferFailure, ApplyTransferService
from api.services.current_squad import (
    CurrentSquadPlayerSelection,
    UpsertCurrentSquadRequest,
    UpsertCurrentSquadService,
)
from api.services.get_my_team_view import MyTeamViewRecord
from conftest import requires_database, seed_planner_players
from fpl_engine.rules import RuleViolationError
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = requires_database

DRIFTED_BANK = 0.5000000000000062


def _saves() -> list[CurrentSquadPlayerSave]:
    # Players 1-15 of the planner fixture form a legal 1-4-4-2 XI plus a four-man bench.
    return [
        CurrentSquadPlayerSave(
            player_id=number,
            is_starting=number <= 11,
            bench_order=None if number <= 11 else number - 11,
            is_captain=number == 2,
            is_vice_captain=number == 3,
        )
        for number in range(1, 16)
    ]


def _seed_squad(session: Session, metadata: dict, *, bank: float) -> None:
    seed_planner_players(session, metadata)
    CurrentSquadRepository(session).save_current(bank=bank, free_transfers=1, players=_saves())
    session.commit()


def _stored_bank(session: Session) -> float:
    return float(session.scalar(select(SquadModel.bank)))


def test_put_stores_the_exact_tenth_for_a_drifted_bank_and_leaves_invalid_rows_untouched(
    planner_session: Session, planner_metadata: dict
) -> None:
    _seed_squad(planner_session, planner_metadata, bank=DRIFTED_BANK)
    assert _stored_bank(planner_session) == DRIFTED_BANK
    service = UpsertCurrentSquadService(
        CurrentSquadRepository(planner_session), SquadPlayerLookupRepository(planner_session)
    )
    players = [
        CurrentSquadPlayerSelection(
            save.player_id,
            save.is_starting,
            save.bench_order,
            save.is_captain,
            save.is_vice_captain,
        )
        for save in _saves()
    ]

    with pytest.raises(RuleViolationError) as error:
        service.execute(UpsertCurrentSquadRequest(bank=0.55, free_transfers=1, players=players))
    planner_session.rollback()
    assert error.value.code == "invalid_money"
    assert _stored_bank(planner_session) == DRIFTED_BANK

    # A rearrangement echoes the loaded (drifted) bank back; the save normalises it.
    service.execute(UpsertCurrentSquadRequest(bank=DRIFTED_BANK, free_transfers=1, players=players))
    planner_session.commit()

    stored = _stored_bank(planner_session)
    assert stored == 0.5
    assert repr(stored) == "0.5"


class _Runs:
    def get_latest(self, model_version: str) -> ProjectionRunRecord:
        now = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.UTC)
        return ProjectionRunRecord(
            id=1,
            model_version=model_version,
            generated_at=now,
            gameweeks_covered=[5],
            parameters={},
            team_strength_snapshot={},
            player_snapshot_generated_at=now,
        )


class _Projections:
    def list_player_fixture_projections_for_run(
        self, player_ids: list[int], run_id: int
    ) -> list[PlayerProjectionFixtureRecord]:
        return [
            PlayerProjectionFixtureRecord(
                player_id=player_id,
                fixture_id=1000 + player_id,
                gameweek_number=5,
                projected_points=2.0 + (player_id % 7) / 10,
                kickoff_time="2026-09-20T15:00:00+00:00",
                opponent_team_short_name="CHE",
                is_home=True,
            )
            for player_id in player_ids
        ]


class _Players:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, player_id: int) -> CandidatePlayerRecord | None:
        player = self._session.get(PlayerModel, player_id)
        if player is None:
            return None
        return CandidatePlayerRecord(
            player_id=player.id,
            web_name=player.web_name,
            team_id=player.team_id,
            team_short_name=f"T{player.team_id}",
            current_price=float(player.current_price),
            position=player.position.value,
            status=player.status,
            can_select=True,
            can_transact=True,
        )


class _View:
    def execute(self) -> MyTeamViewRecord:
        return MyTeamViewRecord(
            squad_id=1,
            name="My Team",
            bank=0.0,
            free_transfers=1,
            players=[],
            projection_totals=None,
            bench_projection_totals=None,
            captain_adjusted_projection_totals=None,
            gameweek_numbers=[5],
        )


def test_a_chain_of_applied_transfers_persists_only_exact_tenth_banks(
    planner_session: Session, planner_metadata: dict
) -> None:
    _seed_squad(planner_session, planner_metadata, bank=0.5)
    # Midfielders 14 (squad) then 106..109 (the copies of 6-9 outside the squad), mixed tenths.
    tenths = {14: 50, 106: 51, 107: 53, 108: 49, 109: 52}
    for player_id, price in tenths.items():
        planner_session.get(PlayerModel, player_id).current_price = price / 10
    planner_session.commit()
    service = ApplyTransferService(
        CurrentSquadRepository(planner_session),
        _Runs(),
        _Projections(),
        _Players(planner_session),
        _View(),
    )

    bank_tenths = 5
    chain = [14, 106, 107, 108, 109]
    for outgoing, incoming in pairwise(chain):
        result = service.execute(outgoing, incoming)
        assert not isinstance(result, ApplyTransferFailure), result
        planner_session.commit()
        bank_tenths += tenths[outgoing] - tenths[incoming]

        stored = _stored_bank(planner_session)
        assert Decimal(str(stored)) * 10 == bank_tenths
        assert repr(stored) == repr(bank_tenths / 10)


def test_apply_rejects_an_invalid_persisted_bank_without_writing(
    planner_session: Session, planner_metadata: dict
) -> None:
    _seed_squad(planner_session, planner_metadata, bank=0.55)
    service = ApplyTransferService(
        CurrentSquadRepository(planner_session),
        _Runs(),
        _Projections(),
        _Players(planner_session),
        _View(),
    )

    result = service.execute(14, 106)

    assert isinstance(result, ApplyTransferFailure)
    assert result.code == "invalid_money"
    planner_session.rollback()
    assert _stored_bank(planner_session) == 0.55
