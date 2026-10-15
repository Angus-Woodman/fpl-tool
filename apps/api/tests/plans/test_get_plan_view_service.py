from __future__ import annotations

import pytest
from api.repositories.my_team_projection_repository import PlayerProjectionFixtureRecord
from api.repositories.plan_repository import (
    PlanGameweekRecord,
    PlanPlayerRecord,
    PlanRecord,
)
from api.services.get_plan_view import GetPlanViewService
from builders import POSITIONS, PRICES, build_squad


class _FakeProjectionRepository:
    def __init__(self, rows: list[PlayerProjectionFixtureRecord]) -> None:
        self._rows = rows

    def list_latest_player_fixture_projections(
        self, player_ids: list[int]
    ) -> list[PlayerProjectionFixtureRecord]:
        return [row for row in self._rows if row.player_id in set(player_ids)]


def _projection(
    player_id: int, gameweek_number: int, points: float
) -> PlayerProjectionFixtureRecord:
    return PlayerProjectionFixtureRecord(
        player_id=player_id,
        fixture_id=player_id * 100 + gameweek_number,
        gameweek_number=gameweek_number,
        projected_points=points,
        kickoff_time="2026-08-15T14:00:00+00:00",
        opponent_team_short_name="OPP",
        is_home=True,
    )


def _plan(chip: str | None = None, points_hit: int = 0) -> PlanRecord:
    players = [
        PlanPlayerRecord(
            player_id=player.player_id,
            web_name=f"P{player.player_id}",
            first_name="First",
            second_name="Second",
            team_id=player.player_id,
            team_name=f"Team {player.player_id}",
            team_short_name="TMX",
            position=POSITIONS[player.player_id],
            current_price=PRICES[player.player_id],
            status="a",
            is_starting=player.is_starting,
            bench_order=player.bench_order,
            is_captain=player.is_captain,
            is_vice_captain=player.is_vice_captain,
        )
        for player in build_squad()
    ]
    return PlanRecord(
        plan_id=1,
        name="No Haaland GW1",
        start_gameweek=1,
        end_gameweek=1,
        initial_bank=0.5,
        initial_free_transfers=1,
        gameweeks=[
            PlanGameweekRecord(
                gameweek_number=1,
                chip=chip,
                bank=0.5,
                free_transfers_available=1,
                transfers_made=0,
                points_hit=points_hit,
                players=players,
            )
        ],
    )


def _projections() -> list[PlayerProjectionFixtureRecord]:
    return [_projection(player_id, 1, 2.0) for player_id in range(1, 16)]


def test_starters_and_captain_are_projected() -> None:
    service = GetPlanViewService(_FakeProjectionRepository(_projections()))

    view = service.execute(_plan())

    gameweek = view.gameweeks[0]
    assert gameweek.starting_points == 22.0
    assert gameweek.captain_bonus_points == 2.0
    assert gameweek.total_points == 24.0
    assert view.total_points == 24.0


def test_bench_boost_adds_the_bench() -> None:
    service = GetPlanViewService(_FakeProjectionRepository(_projections()))

    view = service.execute(_plan(chip="BENCH_BOOST"))

    assert view.gameweeks[0].bench_points == 8.0
    assert view.gameweeks[0].total_points == 32.0


def test_triple_captain_triples_the_captain() -> None:
    service = GetPlanViewService(_FakeProjectionRepository(_projections()))

    view = service.execute(_plan(chip="TRIPLE_CAPTAIN"))

    assert view.gameweeks[0].captain_bonus_points == 4.0


def test_points_hit_is_deducted_from_the_gameweek_total() -> None:
    service = GetPlanViewService(_FakeProjectionRepository(_projections()))

    view = service.execute(_plan(points_hit=4))

    assert view.gameweeks[0].total_points == 20.0
    assert view.total_points_hit == 4


def test_double_gameweek_points_are_summed_for_a_player() -> None:
    rows = [*_projections(), _projection(13, 1, 3.0)]
    service = GetPlanViewService(_FakeProjectionRepository(rows))

    view = service.execute(_plan())

    captain = next(player for player in view.gameweeks[0].players if player.is_captain)
    assert captain.projected_points == 5.0
    assert len(captain.fixtures) == 2


@pytest.mark.parametrize("free_hit", [False, True])
def test_us3_explicit_decisions_and_accounting_ignore_legacy_snapshots(
    planner_plan, planner_metadata, free_hit
) -> None:
    from dataclasses import replace
    from uuid import UUID

    from fpl_engine.planning.models import TransferDecision
    from fpl_engine.rules import Chip

    decision = TransferDecision(
        UUID(int=8000),
        2,
        UUID(int=1002),
        102,
        UUID(int=8001),
        54,
        50,
        "stored_market",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )
    plan = replace(
        planner_plan,
        boundary=replace(planner_plan.boundary, free_transfers=0),
        gameweeks=(
            replace(
                planner_plan.gameweeks[0],
                transfers=(decision,),
                chip=Chip.FREE_HIT if free_hit else None,
            ),
            *planner_plan.gameweeks[1:],
        ),
    )
    players = [
        PlanPlayerRecord(
            identifier,
            f"P{identifier}",
            "First",
            "Second",
            player.team_id,
            "Team",
            "TMX",
            player.position.value,
            9.9,
            "a",
            False,
            None,
            False,
            False,
        )
        for identifier, player in planner_metadata.items()
    ]
    record = replace(
        _plan(),
        canonical_plan=plan,
        rule_players=players,
        initial_bank=99.9,
        initial_free_transfers=5,
    )
    view = GetPlanViewService(_FakeProjectionRepository([])).execute(record)
    assert view.gameweeks[0].accounting == {
        "starting_bank_tenths": 10,
        "closing_bank_tenths": 12,
        "free_transfers_available": 0,
        "next_free_transfers": 1,
        "unlimited_transfers": free_hit,
        "transfers_made": 1,
        "points_hit": 0 if free_hit else 4,
    }
    assert [item.player_id for item in view.gameweeks[0].transfers_out] == [2]
    assert [item.player_id for item in view.gameweeks[0].transfers_in] == [102]
    assert view.gameweeks[1].transfers_in == []
    assert view.gameweeks[1].transfers_out == []
    assert view.gameweeks[1].bank == (1.0 if free_hit else 1.2)
    assert view.gameweeks[1].transfers_made == 0
    assert view.total_points_hit == (0 if free_hit else 4)


@pytest.mark.parametrize("blocked", [False, True])
def test_canonical_view_uses_replay_not_quarantined_finances(
    planner_plan, planner_metadata, blocked
) -> None:
    from dataclasses import replace
    from uuid import UUID

    from api.schemas.plans import PlanResponse
    from fpl_engine.planning.models import TransferDecision

    if blocked:
        bad = TransferDecision(
            UUID(int=8000),
            2,
            UUID(int=9000),
            102,
            UUID(int=8001),
            54,
            50,
            "stored_market",
            "2026-10-14T12:00:00+00:00",
            "legacy_initialized_estimate",
        )
        planner_plan = replace(
            planner_plan,
            gameweeks=(
                replace(planner_plan.gameweeks[0], transfers=(bad,)),
                *planner_plan.gameweeks[1:],
            ),
        )

    players = [
        PlanPlayerRecord(
            identifier,
            f"P{identifier}",
            "First",
            "Second",
            player.team_id,
            f"Team {player.team_id}",
            "TMX",
            player.position.value,
            9.9,
            "a",
            False,
            None,
            False,
            False,
        )
        for identifier, player in planner_metadata.items()
    ]
    record = replace(
        _plan(),
        canonical_plan=planner_plan,
        rule_players=players,
        initial_bank=99.9,
        initial_free_transfers=5,
    )
    view = GetPlanViewService(_FakeProjectionRepository([])).execute(record)
    response = PlanResponse.model_validate(view).model_dump(mode="json")
    assert response["foundation_state"] == "ready"
    assert response["starting_state"]["bank_tenths"] == 10
    assert response["gameweeks"][0]["accounting"]["closing_bank_tenths"] == (
        None if blocked else 10
    )
    assert response["gameweeks"][0]["free_transfers_available"] == 1
    if blocked:
        assert not response["gameweeks"][0]["players"]
        assert response["gameweeks"][0]["total_points"] is None
        assert response["total_points"] is None
        assert response["gameweeks"][1]["accounting"]["closing_bank_tenths"] is None
    else:
        assert response["gameweeks"][0]["players"][0]["ownership_id"] is not None
    assert response["gameweeks"][0]["chip_availability"]["WILDCARD"]["state"] == "available"


def test_us4_decision_inspection_separates_basis_saved_quotes_and_live_prices(
    planner_plan, planner_metadata
) -> None:
    from dataclasses import replace
    from uuid import UUID

    from fpl_engine.planning.models import TransferDecision

    decision = TransferDecision(
        UUID(int=8000),
        2,
        UUID(int=1002),
        102,
        UUID(int=8001),
        54,
        62,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )
    corrected = tuple(
        replace(
            player,
            purchase_price_tenths=48,
            provenance=replace(player.provenance, confirmation="user_confirmed"),
        )
        if player.player_id == 2
        else player
        for player in planner_plan.boundary.players
    )
    plan = replace(
        planner_plan,
        boundary=replace(planner_plan.boundary, players=corrected),
        gameweeks=(
            replace(planner_plan.gameweeks[0], transfers=(decision,)),
            *planner_plan.gameweeks[1:],
        ),
    )
    live = {2: 5.6, 102: 6.0}
    players = [
        PlanPlayerRecord(
            identifier,
            f"P{identifier}",
            "First",
            "Second",
            player.team_id,
            "Team",
            "TMX",
            player.position.value,
            live.get(identifier, 5.0),
            "a",
            False,
            None,
            False,
            False,
        )
        for identifier, player in planner_metadata.items()
    ]
    record = replace(_plan(), canonical_plan=plan, rule_players=players)
    view = GetPlanViewService(_FakeProjectionRepository([])).execute(record)
    saved = view.gameweeks[0].decisions[0]
    assert (saved["purchase_price_tenths"], saved["basis_kind"], saved["basis_confirmation"]) == (
        48,
        "starting",
        "user_confirmed",
    )
    assert (saved["outgoing_market_tenths"], saved["selling_price_tenths"]) == (54, 51)
    assert saved["incoming_price_tenths"] == 62
    assert (saved["outgoing_live_market_tenths"], saved["incoming_live_price_tenths"]) == (56, 60)
    assert view.gameweeks[0].accounting["closing_bank_tenths"] == -1
    status = view.financial_status
    assert status["provisional"] is True
    assert status["requires_resolution"] is True
    assert status["earliest_shortfall_gameweek"] == 8
    assert status["earliest_shortfall_tenths"] == 1
    assert "gameweek 8" in str(status["earliest_shortfall_reason"])
    assert "0.1" in str(status["earliest_shortfall_reason"])
    weeks = status["gameweeks"]
    assert [week["shortfall_tenths"] for week in weeks][:2] == [1, 1]
    assert weeks[0]["provisional"] is True
    assert weeks[1]["affected_chain"] == [8, 9]


def test_us4_resolved_plan_has_no_shortfall_reason_or_amount(
    planner_plan, planner_metadata
) -> None:
    from dataclasses import replace

    players = [
        PlanPlayerRecord(
            identifier,
            f"P{identifier}",
            "First",
            "Second",
            player.team_id,
            "Team",
            "TMX",
            player.position.value,
            5.0,
            "a",
            False,
            None,
            False,
            False,
        )
        for identifier, player in planner_metadata.items()
    ]
    record = replace(_plan(), canonical_plan=planner_plan, rule_players=players)
    status = GetPlanViewService(_FakeProjectionRepository([])).execute(record).financial_status
    assert status["requires_resolution"] is False
    assert status["earliest_shortfall_gameweek"] is None
    assert status["earliest_shortfall_tenths"] is None
    assert status["earliest_shortfall_reason"] is None


@pytest.mark.parametrize("live", [0.0, -1.0, 5.55, float("nan"), float("inf")])
def test_us4_unusable_live_prices_never_break_the_read_or_invent_a_value(
    planner_plan, planner_metadata, live
) -> None:
    from dataclasses import replace
    from uuid import UUID

    from api.schemas.plans import TransferDecisionResponse
    from fpl_engine.planning.models import TransferDecision

    decision = TransferDecision(
        UUID(int=8000),
        2,
        UUID(int=1002),
        102,
        UUID(int=8001),
        54,
        50,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )
    plan = replace(
        planner_plan,
        gameweeks=(
            replace(planner_plan.gameweeks[0], transfers=(decision,)),
            *planner_plan.gameweeks[1:],
        ),
    )
    players = [
        PlanPlayerRecord(
            identifier,
            f"P{identifier}",
            "First",
            "Second",
            player.team_id,
            "Team",
            "TMX",
            player.position.value,
            live if identifier in (2, 102) else 5.0,
            "a",
            False,
            None,
            False,
            False,
        )
        for identifier, player in planner_metadata.items()
    ]
    record = replace(_plan(), canonical_plan=plan, rule_players=players)
    saved = (
        GetPlanViewService(_FakeProjectionRepository([])).execute(record).gameweeks[0].decisions[0]
    )
    assert saved["outgoing_live_market_tenths"] is None
    assert saved["incoming_live_price_tenths"] is None
    assert (saved["outgoing_market_tenths"], saved["selling_price_tenths"]) == (54, 52)
    assert TransferDecisionResponse.model_validate(saved).incoming_live_price_tenths is None


@pytest.mark.parametrize("bad_side", ["outgoing", "incoming"])
@pytest.mark.parametrize("bad", [0.0, 5.55, float("nan")])
def test_us4_one_unusable_live_price_is_omitted_without_hiding_the_other(
    planner_plan, planner_metadata, bad_side, bad
) -> None:
    from dataclasses import replace
    from uuid import UUID

    from api.schemas.plans import TransferDecisionResponse
    from fpl_engine.planning.models import TransferDecision

    decision = TransferDecision(
        UUID(int=8000),
        2,
        UUID(int=1002),
        102,
        UUID(int=8001),
        54,
        50,
        "stored_player_observation",
        "2026-10-14T12:00:00+00:00",
        "captured",
    )
    plan = replace(
        planner_plan,
        gameweeks=(
            replace(planner_plan.gameweeks[0], transfers=(decision,)),
            *planner_plan.gameweeks[1:],
        ),
    )
    live = {
        2: bad if bad_side == "outgoing" else 5.6,
        102: bad if bad_side == "incoming" else 6.0,
    }
    players = [
        PlanPlayerRecord(
            identifier,
            f"P{identifier}",
            "First",
            "Second",
            player.team_id,
            "Team",
            "TMX",
            player.position.value,
            live.get(identifier, 5.0),
            "a",
            False,
            None,
            False,
            False,
        )
        for identifier, player in planner_metadata.items()
    ]
    record = replace(_plan(), canonical_plan=plan, rule_players=players)
    saved = (
        GetPlanViewService(_FakeProjectionRepository([])).execute(record).gameweeks[0].decisions[0]
    )
    expected = {"outgoing": (None, 60), "incoming": (56, None)}[bad_side]
    assert (saved["outgoing_live_market_tenths"], saved["incoming_live_price_tenths"]) == expected
    assert (saved["outgoing_market_tenths"], saved["incoming_price_tenths"]) == (54, 50)
    assert saved["selling_price_tenths"] == 52
    TransferDecisionResponse.model_validate(saved)
