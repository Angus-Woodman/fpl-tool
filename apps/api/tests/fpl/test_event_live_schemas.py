import json
from pathlib import Path

import pytest
from api.adapters.fpl.schemas import EventLiveDto
from pydantic import ValidationError

FIXTURE_PATH = Path("data/fixtures/fpl/event_live.json")


def test_event_live_fixture_validates_against_schema() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    dto = EventLiveDto.model_validate(payload)

    assert len(dto.elements) == 2
    assert dto.elements[0].id == 101
    assert dto.elements[0].stats.minutes == 90
    assert dto.elements[0].stats.total_points == 8
    assert dto.elements[0].stats.starts == 1
    assert dto.elements[1].stats.starts == 0


def test_event_live_schema_accepts_unknown_keys() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["elements"][0]["stats"]["a_new_2027_stat"] = 5

    dto = EventLiveDto.model_validate(payload)

    assert dto.elements[0].stats.total_points == 8


def test_event_live_schema_accepts_an_empty_pre_season_response() -> None:
    dto = EventLiveDto.model_validate({"elements": []})

    assert dto.elements == []


def test_event_live_schema_defaults_absent_stats_to_zero() -> None:
    dto = EventLiveDto.model_validate({"elements": [{"id": 7, "stats": {}}]})

    stats = dto.elements[0].stats
    assert stats.minutes == 0
    assert stats.total_points == 0
    assert stats.bps == 0
    assert stats.starts == 0


def test_event_live_schema_rejects_an_element_without_an_id() -> None:
    with pytest.raises(ValidationError):
        EventLiveDto.model_validate({"elements": [{"stats": {"minutes": 90}}]})
