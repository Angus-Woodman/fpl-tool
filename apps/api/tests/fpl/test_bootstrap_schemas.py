import json
from pathlib import Path

import pytest
from api.adapters.fpl.schemas import BootstrapStaticDto
from pydantic import ValidationError

FIXTURE_PATH = Path("data/fixtures/fpl/bootstrap_static.json")


def test_bootstrap_fixture_validates_against_schema() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    dto = BootstrapStaticDto.model_validate(payload)

    assert len(dto.teams) == 2
    assert len(dto.elements) == 2
    assert len(dto.events) == 2


def test_bootstrap_schema_accepts_unknown_keys() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["teams"][0]["unexpected"] = "field"

    dto = BootstrapStaticDto.model_validate(payload)

    assert len(dto.teams) == 2


def test_bootstrap_schema_rejects_missing_required_fields() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    del payload["teams"][0]["short_name"]

    with pytest.raises(ValidationError):
        BootstrapStaticDto.model_validate(payload)
