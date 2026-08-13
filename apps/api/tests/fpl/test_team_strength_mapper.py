from __future__ import annotations

from api.adapters.fpl.mappers import map_bootstrap_static
from api.adapters.fpl.schemas import BootstrapStaticDto


def _payload(team: dict[str, object]) -> BootstrapStaticDto:
    return BootstrapStaticDto.model_validate(
        {
            "teams": [{"id": 1, "name": "Arsenal", "short_name": "ARS", **team}],
            "elements": [],
            "events": [],
        }
    )


def test_derives_difficulty_from_overall_strength() -> None:
    mapped = map_bootstrap_static(
        _payload({"strength_overall_home": 4, "strength_overall_away": 4})
    )

    team = mapped.teams[0]
    assert team.source_difficulty == 4
    assert team.strength_overall_home == 4
    assert team.strength_overall_away == 4


def test_averages_differing_home_and_away_strength() -> None:
    mapped = map_bootstrap_static(
        _payload({"strength_overall_home": 4, "strength_overall_away": 5})
    )

    assert mapped.teams[0].source_difficulty == 5


def test_averages_down_when_home_is_weaker() -> None:
    mapped = map_bootstrap_static(
        _payload({"strength_overall_home": 2, "strength_overall_away": 3})
    )

    assert mapped.teams[0].source_difficulty == 3


def test_falls_back_to_legacy_strength_when_overall_is_absent() -> None:
    mapped = map_bootstrap_static(_payload({"strength": 5}))

    assert mapped.teams[0].source_difficulty == 5


def test_defaults_when_no_strength_signal_is_present() -> None:
    mapped = map_bootstrap_static(_payload({}))

    team = mapped.teams[0]
    assert team.source_difficulty == 3
    assert team.strength_overall_home is None


def test_clamps_out_of_range_values() -> None:
    mapped = map_bootstrap_static(
        _payload({"strength_overall_home": 9, "strength_overall_away": 9})
    )

    assert mapped.teams[0].source_difficulty == 5


def test_ignores_zero_placeholders() -> None:
    mapped = map_bootstrap_static(
        _payload({"strength_overall_home": 0, "strength_overall_away": 0, "strength": 4})
    )

    assert mapped.teams[0].source_difficulty == 4
