import json
from pathlib import Path

import pytest
from api.adapters.fpl.schemas import FplFixtureDto
from pydantic import ValidationError

FIXTURE_PATH = Path("data/fixtures/fpl/fixtures.json")


def test_fixtures_fixture_validates_against_schema() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    fixtures = [FplFixtureDto.model_validate(item) for item in payload]

    assert len(fixtures) == 2


def test_fixtures_schema_rejects_missing_required_field() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    del payload[0]["team_h"]

    with pytest.raises(ValidationError):
        FplFixtureDto.model_validate(payload[0])
