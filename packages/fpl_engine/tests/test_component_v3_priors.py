from __future__ import annotations

import pytest
from fpl_engine.domain import PlayerPosition
from fpl_engine.projections.component_v3_priors import (
    DEFAULT_TEAM_DEFENSE_PRIOR_PARAMETERS,
    GoalkeeperSavesHistory,
    PlayerHistoryForTeamDefense,
    TeamDefensePriorParameters,
    compute_saves_prior,
    compute_team_defense_priors,
)

CS_PRIOR_BY_STRENGTH = {1: 0.15, 2: 0.20, 3: 0.25, 4: 0.32, 5: 0.42}


def _history(
    *,
    team_id: int,
    position: PlayerPosition = PlayerPosition.GOALKEEPER,
    clean_sheets_per_90: float,
    total_minutes: float,
) -> PlayerHistoryForTeamDefense:
    return PlayerHistoryForTeamDefense(
        team_id=team_id,
        position=position,
        clean_sheets_per_90=clean_sheets_per_90,
        total_minutes=total_minutes,
    )


class TestGoalkeeperOnlyDefault:
    def test_defender_history_is_ignored_by_default(self) -> None:
        histories = [
            _history(
                team_id=1,
                position=PlayerPosition.GOALKEEPER,
                clean_sheets_per_90=0.5,
                total_minutes=3000,
            ),
            _history(
                team_id=1,
                position=PlayerPosition.DEFENDER,
                clean_sheets_per_90=0.1,
                total_minutes=3000,
            ),
        ]

        resolved = compute_team_defense_priors(
            histories,
            team_source_difficulty={1: 5},
            cs_prior_by_strength=CS_PRIOR_BY_STRENGTH,
        )

        expected = (
            3000 * 0.5 + DEFAULT_TEAM_DEFENSE_PRIOR_PARAMETERS.team_cs_m0 * CS_PRIOR_BY_STRENGTH[5]
        ) / (3000 + DEFAULT_TEAM_DEFENSE_PRIOR_PARAMETERS.team_cs_m0)
        assert resolved[1].clean_sheet_rate == pytest.approx(expected)

    def test_defense_history_positions_is_configurable(self) -> None:
        histories = [
            _history(
                team_id=1,
                position=PlayerPosition.GOALKEEPER,
                clean_sheets_per_90=0.5,
                total_minutes=3000,
            ),
            _history(
                team_id=1,
                position=PlayerPosition.DEFENDER,
                clean_sheets_per_90=0.1,
                total_minutes=3000,
            ),
        ]
        parameters = TeamDefensePriorParameters(
            team_cs_m0=900.0,
            defense_history_positions=frozenset(
                {PlayerPosition.GOALKEEPER, PlayerPosition.DEFENDER}
            ),
        )

        resolved = compute_team_defense_priors(
            histories,
            team_source_difficulty={1: 5},
            cs_prior_by_strength=CS_PRIOR_BY_STRENGTH,
            parameters=parameters,
        )

        expected_observed = (3000 * 0.5 + 3000 * 0.1) / (3000 + 3000)
        expected = (6000 * expected_observed + 900.0 * CS_PRIOR_BY_STRENGTH[5]) / (6000 + 900.0)
        assert resolved[1].clean_sheet_rate == pytest.approx(expected)


class TestFallbackForTeamsWithNoHistory:
    def test_a_team_with_no_goalkeeper_history_resolves_to_exactly_the_prior(self) -> None:
        resolved = compute_team_defense_priors(
            [],
            team_source_difficulty={7: 2},
            cs_prior_by_strength=CS_PRIOR_BY_STRENGTH,
        )

        assert resolved[7].clean_sheet_rate == CS_PRIOR_BY_STRENGTH[2]
        assert resolved[7].observed_history_weight == 0.0
        assert resolved[7].source_difficulty_used == 2

    def test_every_team_in_the_strength_mapping_gets_a_resolved_entry(self) -> None:
        histories = [
            _history(team_id=1, clean_sheets_per_90=0.5, total_minutes=3000),
        ]

        resolved = compute_team_defense_priors(
            histories,
            team_source_difficulty={1: 5, 2: 3, 3: 1},
            cs_prior_by_strength=CS_PRIOR_BY_STRENGTH,
        )

        assert set(resolved.keys()) == {1, 2, 3}


class TestAbundantHistoryStaysCloseToOwnRate:
    def test_a_full_season_of_goalkeeper_minutes_dominates_the_shrunk_estimate(self) -> None:
        histories = [
            _history(team_id=1, clean_sheets_per_90=0.5, total_minutes=3420),
        ]

        resolved = compute_team_defense_priors(
            histories,
            team_source_difficulty={1: 3},
            cs_prior_by_strength=CS_PRIOR_BY_STRENGTH,
            parameters=TeamDefensePriorParameters(team_cs_m0=100.0),
        )

        assert resolved[1].observed_history_weight > 0.9
        assert resolved[1].clean_sheet_rate == pytest.approx(0.5, abs=0.05)


class TestExposureWeightingAcrossMultipleGoalkeepers:
    def test_two_goalkeepers_are_weighted_by_their_own_minutes(self) -> None:
        histories = [
            _history(team_id=1, clean_sheets_per_90=0.6, total_minutes=2700),
            _history(team_id=1, clean_sheets_per_90=0.2, total_minutes=900),
        ]
        parameters = TeamDefensePriorParameters(team_cs_m0=900.0)

        resolved = compute_team_defense_priors(
            histories,
            team_source_difficulty={1: 3},
            cs_prior_by_strength=CS_PRIOR_BY_STRENGTH,
            parameters=parameters,
        )

        observed = (2700 * 0.6 + 900 * 0.2) / (2700 + 900)
        expected = (3600 * observed + 900.0 * CS_PRIOR_BY_STRENGTH[3]) / (3600 + 900.0)
        assert resolved[1].clean_sheet_rate == pytest.approx(expected)


class TestComputeSavesPrior:
    def test_exposure_weighted_across_goalkeepers(self) -> None:
        histories = [
            GoalkeeperSavesHistory(saves_per_90=3.0, total_minutes=3000),
            GoalkeeperSavesHistory(saves_per_90=1.0, total_minutes=1000),
        ]

        prior = compute_saves_prior(histories)

        assert prior == pytest.approx((3000 * 3.0 + 1000 * 1.0) / (3000 + 1000))

    def test_raises_when_no_goalkeeper_has_minutes(self) -> None:
        with pytest.raises(ValueError):
            compute_saves_prior([GoalkeeperSavesHistory(saves_per_90=2.0, total_minutes=0)])

        with pytest.raises(ValueError):
            compute_saves_prior([])
