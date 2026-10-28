from __future__ import annotations

import copy
import inspect
from collections.abc import Mapping

import pytest
from api.services.plan_context import PlanningContext
from api.services.plan_transfer_analysis import (
    PlanTransferAnalysisService,
    PlanTransferFailure,
    PlanTransferList,
    PlanTransferPreview,
)
from explorer_builders import (
    CLUB_LIMIT_CANDIDATE,
    FakeLookup,
    FakePlayers,
    FakeProjections,
    FakeRuns,
    FakeTeams,
    candidate_records,
    context_for,
    flat_points,
    identity,
    plan,
    reference_scenarios,
    run_record,
    transfer,
)
from fpl_engine.rules import Chip

SPECIAL = {6: 2.0, 106: 5.0}


def make_service(
    points: Mapping[int, Mapping[int, float]] | None = None,
    *,
    records: list | None = None,
    runs: FakeRuns | None = None,
) -> tuple[PlanTransferAnalysisService, FakeProjections]:
    projections = FakeProjections(
        points if points is not None else flat_points(range(8, 14), SPECIAL)
    )
    return (
        PlanTransferAnalysisService(
            players=FakePlayers(records),
            lookup=FakeLookup(records),
            runs=runs if runs is not None else FakeRuns(run_record()),
            projections=projections,
            teams=FakeTeams(),
        ),
        projections,
    )


def scenario_context(name: str, gameweek: int | None = None) -> PlanningContext:
    scenario = next(item for item in reference_scenarios() if item.name == name)
    return context_for(scenario.plan, gameweek if gameweek is not None else scenario.gameweek)


def listed(
    context: PlanningContext,
    out: int,
    *,
    service: PlanTransferAnalysisService | None = None,
    **options: int | None,
) -> PlanTransferList:
    result = (service or make_service()[0]).list_candidates(context, out, **options)
    assert isinstance(result, PlanTransferList), result
    return result


def failure(result: object) -> PlanTransferFailure:
    assert isinstance(result, PlanTransferFailure), result
    return result


def test_the_service_is_built_only_from_read_only_ports() -> None:
    parameters = set(inspect.signature(PlanTransferAnalysisService).parameters)
    assert parameters == {"players", "lookup", "runs", "projections", "teams"}
    service, _ = make_service()
    names = {name for name in dir(service) if not name.startswith("_")}
    assert {"list_candidates"} <= names <= {"list_candidates", "preview"}


def test_the_pool_follows_my_team_rules() -> None:
    result = listed(scenario_context("ordinary"), 6)
    pool = {candidate.player_id for candidate in result.candidates}
    assert pool == {106, 107, 108, 109, 114, CLUB_LIMIT_CANDIDATE}
    assert all(candidate.position == "MID" for candidate in result.candidates)


def test_known_non_selectable_candidates_are_excluded_and_playing_status_is_advisory() -> None:
    records = candidate_records(overrides={109: {"can_select": False}, 107: {"status": "i"}})
    service, _ = make_service(records=records)
    result = listed(scenario_context("ordinary"), 6, service=service)
    by_id = {candidate.player_id: candidate for candidate in result.candidates}
    assert 109 not in by_id
    assert by_id[107].status == "i"
    assert by_id[107].state == "available"


def test_unknown_selectability_is_the_refresh_required_failure() -> None:
    records = candidate_records(overrides={114: {"can_select": None}})
    service, _ = make_service(records=records)
    result = failure(service.list_candidates(scenario_context("ordinary"), 6))
    assert result.code == "selectability_unknown"
    assert "refresh" in result.message.lower()


def test_the_projection_run_is_pinned_and_a_newer_run_is_disclosed() -> None:
    runs = FakeRuns(run_record(1, hours=0), run_record(2, hours=5))
    service, projections = make_service(runs=runs)
    latest = listed(scenario_context("ordinary"), 6, service=service)
    assert (latest.projection.run_id, latest.projection.newer_run_available) == (2, False)
    pinned = listed(scenario_context("ordinary"), 6, service=service, projection_run_id=1)
    assert (pinned.projection.run_id, pinned.projection.newer_run_available) == (1, True)
    assert projections.calls[-1] == (1, 8, 12)
    assert pinned.projection.model_version == "component_v3"


@pytest.mark.parametrize(
    ("runs", "pinned", "code"),
    [
        (FakeRuns(), None, "no_projection_run"),
        (FakeRuns(run_record()), 99, "run_not_found"),
        (
            FakeRuns(run_record(1), run_record(3, model_version="baseline_v2")),
            3,
            "run_model_mismatch",
        ),
    ],
)
def test_run_problems_are_explicit_failures(runs: FakeRuns, pinned: int | None, code: str) -> None:
    service, _ = make_service(runs=runs)
    result = service.list_candidates(scenario_context("ordinary"), 6, projection_run_id=pinned)
    assert failure(result).code == code


def test_horizons_are_exactly_the_covered_gameweeks_and_nothing_is_zero_filled() -> None:
    service, _ = make_service(flat_points(range(8, 11), SPECIAL))
    result = listed(scenario_context("ordinary"), 6, service=service)
    horizons = {item.horizon: item for item in result.projection.horizons}
    assert horizons[1].evaluated_gameweeks == [8] and not horizons[1].partial
    assert horizons[3].evaluated_gameweeks == [8, 9, 10] and not horizons[3].partial
    assert horizons[5].requested_gameweeks == [8, 9, 10, 11, 12]
    assert horizons[5].evaluated_gameweeks == [8, 9, 10] and horizons[5].partial
    top = result.candidates[0]
    assert top.best_xi_gain_by_horizon[5] == top.best_xi_gain_by_horizon[3]


def test_a_gap_in_coverage_ends_the_horizon() -> None:
    points = flat_points(range(8, 14), SPECIAL)
    del points[10]
    result = listed(scenario_context("ordinary"), 6, service=make_service(points)[0])
    horizons = {item.horizon: item for item in result.projection.horizons}
    assert horizons[5].evaluated_gameweeks == [8, 9] and horizons[5].partial


def test_unprojected_gameweek_missing_squad_projection_and_unknown_player_are_explicit() -> None:
    context = scenario_context("ordinary")
    no_rows = make_service(flat_points(range(9, 14), SPECIAL))[0].list_candidates(context, 6)
    assert failure(no_rows).code == "gameweek_not_projected"

    points = flat_points(range(8, 14), SPECIAL)
    for week in points.values():
        del week[5]
    missing = failure(make_service(points)[0].list_candidates(context, 6))
    assert missing.code == "missing_projections" and missing.missing_player_ids == (5,)

    absent = failure(make_service()[0].list_candidates(context, 107))
    assert absent.code == "player_not_in_squad"


def test_candidates_are_ranked_by_best_xi_gain_and_unavailable_ones_keep_their_position() -> None:
    points = flat_points(range(8, 14), {6: 2.0, 108: 9.0, CLUB_LIMIT_CANDIDATE: 8.0})
    result = listed(scenario_context("ordinary", 8), 7, service=make_service(points)[0])
    ranked = result.candidates
    assert [item.player_id for item in ranked[:2]] == [108, CLUB_LIMIT_CANDIDATE]
    assert [(item.best_xi_gain_by_horizon[5], -item.player_id) for item in ranked] == sorted(
        ((item.best_xi_gain_by_horizon[5], -item.player_id) for item in ranked), reverse=True
    )
    by_id = {item.player_id: item for item in ranked}
    assert by_id[108].state == "unavailable" and by_id[108].reasons == ["financial_shortfall"]
    assert by_id[CLUB_LIMIT_CANDIDATE].state == "unavailable"
    assert by_id[CLUB_LIMIT_CANDIDATE].reasons == ["club_limit"]
    assert by_id[106].state == "available"


def test_plan_impact_uses_the_plan_and_keeps_assumed_continuation_separate() -> None:
    points = flat_points(range(8, 13), SPECIAL)
    result = listed(scenario_context("ordinary"), 6, service=make_service(points)[0])
    candidate = next(item for item in result.candidates if item.player_id == 106)
    impact = candidate.plan_impact_by_horizon
    assert impact[1].saved_plan == 3.0
    assert impact[3].saved_plan == 9.0
    assert impact[5].saved_plan == 12.0  # GW8 to GW11
    assert impact[5].assumed_continuation == 3.0  # GW12, after the plan's end
    assert impact[5].net_saved_plan == 12.0
    assert impact[1].assumed_continuation is None
    assert candidate.best_xi_gain_by_horizon[1] > 0
    assert candidate.direct_xpts_difference == 3.0


def test_a_later_conflict_blocks_and_limits_values_to_the_valid_range() -> None:
    result = listed(scenario_context("later_sale_of_a_player"), 6)
    candidate = next(item for item in result.candidates if item.player_id == 106)
    assert candidate.state == "blocked_by_later_decision"
    assert candidate.conflict is not None and candidate.conflict.gameweek == 10
    assert candidate.conflict.kind == "structural"
    assert candidate.valid_through_gameweek == 9
    assert candidate.plan_impact_by_horizon[5].valid_through_gameweek == 9
    assert candidate.plan_impact_by_horizon[5].saved_plan == 6.0
    assert candidate.plan_impact_by_horizon[5].assumed_continuation is None
    still_ranked = [item.player_id for item in result.candidates]
    assert 106 in still_ranked


def test_estimated_basis_is_provisional_and_the_selling_price_follows_the_official_rule() -> None:
    estimated = listed(scenario_context("estimated_basis"), 6)
    assert estimated.accounting_before.provisional is True
    assert estimated.outgoing.selling_provisional is True
    assert estimated.outgoing.purchase_price_tenths == 50
    assert estimated.outgoing.market_price_tenths == 54
    assert estimated.outgoing.selling_price_tenths == 52
    assert not hasattr(estimated.outgoing, "selling_price_is_approximate")
    confirmed = listed(scenario_context("confirmed_basis"), 6)
    assert confirmed.accounting_before.provisional is False
    assert confirmed.outgoing.selling_provisional is False


def test_accounting_before_reports_the_plan_gameweek_values() -> None:
    accounting = listed(scenario_context("ordinary"), 6).accounting_before
    assert (
        accounting.starting_bank_tenths,
        accounting.closing_bank_tenths,
        accounting.free_transfers_available,
        accounting.transfers_made,
        accounting.points_hit,
        accounting.unlimited_transfers,
    ) == (10, 10, 1, 0, 0, False)


def test_a_free_hit_gameweek_limits_every_horizon_to_that_gameweek() -> None:
    result = listed(scenario_context("free_hit"), 6)
    assert result.projection.limited_to_selected_gameweek is True
    assert result.projection.limited_reason == "free_hit_gameweek"
    assert all(item.evaluated_gameweeks == [9] for item in result.projection.horizons)
    candidate = next(item for item in result.candidates if item.player_id == 106)
    assert candidate.plan_impact_by_horizon[5].saved_plan == 3.0
    assert result.plan.chip == "FREE_HIT"


def test_replacing_a_same_gameweek_acquisition_is_an_edit_without_a_selling_price() -> None:
    result = listed(scenario_context("acquired_earlier_in_same_gameweek"), 102)
    assert result.outgoing.operation == "edit_transfer"
    assert result.outgoing.replaces_decision_id == identity(2001)
    assert result.outgoing.selling_price_tenths is None
    candidate = next(item for item in result.candidates if item.player_id == 105)
    assert candidate.resulting_bank_tenths == 10 + 52 - 50


def test_the_response_identifies_its_planning_context_and_plan() -> None:
    context = scenario_context("ordinary")
    result = listed(context, 6)
    assert result.planning_context == context.ref
    assert result.plan.revision == context.plan.revision == 3
    assert (result.plan.gameweek, result.plan.start_gameweek, result.plan.end_gameweek) == (
        8,
        8,
        11,
    )
    assert result.plan.evaluator_version


def test_candidates_carry_fixtures_with_difficulty_for_the_evaluated_gameweeks() -> None:
    result = listed(scenario_context("ordinary"), 6, primary_horizon=3)
    fixtures = result.candidates[0].fixtures
    assert [item.gameweek for item in fixtures] == [8, 9, 10, 11, 12]
    first = fixtures[0]
    assert (first.opponent_short_name, first.is_home, first.difficulty) == ("O4", True, 4)
    assert result.projection.primary_horizon == 3


def test_money_is_reported_in_whole_tenths() -> None:
    result = listed(scenario_context("ordinary"), 6)
    for candidate in result.candidates:
        assert type(candidate.price_tenths) is int
        if candidate.resulting_bank_tenths is not None:
            assert type(candidate.resulting_bank_tenths) is int
    assert type(result.outgoing.market_price_tenths) is int


def test_analysis_leaves_the_planning_context_unchanged() -> None:
    context = scenario_context("later_purchase_of_a_candidate")
    before_plan, before_baseline = copy.deepcopy(context.plan), copy.deepcopy(context.baseline)
    listed(context, 6)
    assert context.plan == before_plan
    assert context.baseline == before_baseline


def test_the_plan_gameweek_squad_not_my_team_decides_the_pool_and_outgoing_player() -> None:
    reference = plan(transfers={8: (transfer(6, 114, 9),)})
    context = context_for(reference, 9)
    result = listed(context, 114)
    pool = {item.player_id for item in result.candidates}
    assert 6 in pool  # sold in GW8, so a candidate again in GW9
    assert 114 not in pool
    assert result.outgoing.player_id == 114
    assert Chip.FREE_HIT not in {week.chip for week in reference.gameweeks}


def previewed(
    context: PlanningContext,
    out: int,
    incoming: int,
    *,
    service: PlanTransferAnalysisService | None = None,
    **options: int | None,
) -> PlanTransferPreview:
    result = (service or make_service()[0]).preview(context, out, incoming, **options)
    assert isinstance(result, PlanTransferPreview), result
    return result


def rows(preview: PlanTransferPreview) -> dict[int, object]:
    return {row.gameweek: row for row in preview.gameweeks}


def test_a_preview_shows_per_gameweek_accounting_before_and_after() -> None:
    points = flat_points(range(8, 13), SPECIAL)
    preview = previewed(scenario_context("ordinary"), 6, 106, service=make_service(points)[0])

    table = rows(preview)
    first = table[8]
    assert (first.basis, first.valid, first.chip) == ("saved_plan", True, None)
    assert first.accounting is not None
    assert first.accounting.before.closing_bank_tenths == 10
    assert first.accounting.after.closing_bank_tenths == 10 + 52 - 50
    assert (
        first.accounting.before.free_transfers_available,
        first.accounting.before.transfers_made,
    ) == (1, 0)
    assert (first.accounting.after.transfers_made, first.accounting.after.points_hit) == (1, 0)
    assert (
        first.accounting.before.next_free_transfers,
        first.accounting.after.next_free_transfers,
    ) == (2, 1)
    assert first.points.delta == 3.0
    assert first.points.after - first.points.before == 3.0
    assert first.squad_changed is True and first.incoming_role == "starting"
    assert table[12].basis == "assumed_continuation"
    assert table[12].accounting is None and table[12].points.delta == 3.0
    assert preview.totals[3].saved_plan == 9.0
    assert (preview.totals[5].saved_plan, preview.totals[5].assumed_continuation) == (12.0, 3.0)
    assert preview.totals[5].net_saved_plan == 12.0 and preview.totals[5].hit_change == 0


def test_a_hit_is_shown_separately_from_the_saved_plan_impact() -> None:
    preview = previewed(scenario_context("zero_free_transfers", 8), 6, 106)

    assert preview.gameweeks[0].accounting.after.points_hit == 4
    assert preview.totals[1].hit_change == 4
    assert preview.totals[1].saved_plan == 3.0
    assert preview.totals[1].net_saved_plan == -1.0


def test_the_commit_descriptor_is_the_exact_add_operation_pinned_to_the_revision() -> None:
    context = scenario_context("ordinary")
    preview = previewed(context, 6, 106)

    assert preview.confirmable and preview.state == "available"
    commit = preview.commit
    assert commit is not None
    assert (commit.intent.kind, commit.intent.gameweek_number) == ("add_transfer", 8)
    assert (commit.intent.outgoing_player_id, commit.intent.incoming_player_id) == (6, 106)
    assert commit.intent.outgoing_ownership_id == identity(1006)
    assert commit.intent.decision_id is None
    assert (
        commit.guard.expected_outgoing_market_tenths,
        commit.guard.expected_incoming_price_tenths,
    ) == (54, 50)
    assert commit.expected_revision == context.ref.revision == preview.planning_context.revision


def test_replacing_a_same_gameweek_acquisition_previews_as_an_edit_of_that_decision() -> None:
    preview = previewed(scenario_context("acquired_earlier_in_same_gameweek"), 102, 105)

    commit = preview.commit
    assert commit is not None
    assert (commit.intent.kind, commit.intent.decision_id) == ("edit_transfer", identity(2001))
    assert commit.intent.incoming_player_id == 105
    assert commit.intent.outgoing_player_id is None and commit.intent.gameweek_number is None
    assert commit.guard.expected_outgoing_market_tenths == 54  # the decision's own outgoing player


def test_wildcard_is_hit_free_and_permanent_while_free_hit_is_limited_to_its_gameweek() -> None:
    wildcard = previewed(scenario_context("wildcard"), 6, 106)
    table = rows(wildcard)
    assert table[9].accounting.after.points_hit == 0
    assert table[10].squad_changed is True

    free_hit = previewed(scenario_context("free_hit"), 6, 106)
    assert [row.gameweek for row in free_hit.gameweeks] == [9]
    assert free_hit.projection.limited_to_selected_gameweek is True
    assert free_hit.totals[5].assumed_continuation is None

    for name in ("bench_boost", "triple_captain"):
        ordinary = previewed(scenario_context(name), 6, 106)
        assert rows(ordinary)[9].accounting.after.closing_bank_tenths == 10 + 52 - 50
        assert rows(ordinary)[9].accounting.after.points_hit == 0


def test_a_blocked_candidate_shows_values_only_in_range_and_cannot_be_confirmed() -> None:
    preview = previewed(scenario_context("later_sale_of_a_player"), 6, 106)

    assert preview.state == "blocked_by_later_decision"
    assert preview.confirmable is False and preview.commit is None
    assert preview.valid_through_gameweek == 9
    assert preview.conflict is not None
    assert (preview.conflict.gameweek, preview.conflict.decision_id) == (10, identity(2003))
    table = rows(preview)
    assert table[8].valid and table[9].valid
    for number in (10, 11, 12):
        assert not table[number].valid
        assert table[number].reason == "beyond_valid_range"
        assert table[number].accounting is None and table[number].points is None


def test_an_unavailable_candidate_previews_with_its_reasons_and_no_valid_gameweeks() -> None:
    preview = previewed(scenario_context("ordinary"), 7, CLUB_LIMIT_CANDIDATE)

    assert preview.state == "unavailable" and preview.reasons == ["club_limit"]
    assert preview.confirmable is False and preview.commit is None
    assert not any(row.valid for row in preview.gameweeks)


def test_previewing_a_player_outside_the_pool_is_an_explicit_failure() -> None:
    context = scenario_context("ordinary")
    owned = failure(make_service()[0].preview(context, 6, 7))
    assert owned.code == "player_not_in_candidate_pool"
    wrong_position = failure(make_service()[0].preview(context, 6, 101))
    assert wrong_position.code == "player_not_in_candidate_pool"
    missing = failure(make_service()[0].preview(context, 6, 9999))
    assert missing.code == "player_not_found"


def test_the_preview_reports_lineup_effect_and_the_incoming_role() -> None:
    preview = previewed(scenario_context("ordinary"), 2, 102)

    assert preview.lineup_effect.captain_changed is True
    assert preview.lineup_effect.vice_captain_changed is False
    assert rows(preview)[8].incoming_role == "captain"
    assert preview.best_xi.direct_xpts_difference == 0.0
    assert set(preview.best_xi.gain_by_horizon) == {1, 3, 5}


def test_the_preview_never_changes_the_planning_context() -> None:
    context = scenario_context("later_purchase_of_a_candidate")
    before_plan, before_baseline = copy.deepcopy(context.plan), copy.deepcopy(context.baseline)
    previewed(context, 6, 106)
    assert context.plan == before_plan and context.baseline == before_baseline
