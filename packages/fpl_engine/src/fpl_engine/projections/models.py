from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProjectionInput:
    points_per_minute: float
    expected_minutes: float
    fixture_difficulty_multiplier: float


class ProjectionModel(Protocol):
    model_version: str

    def project_points(self, data: ProjectionInput) -> float: ...


@dataclass(frozen=True)
class BaselineProjectionModel:
    model_version: str = "baseline_v1"

    def project_points(self, data: ProjectionInput) -> float:
        raw_points = data.points_per_minute * data.expected_minutes
        return raw_points * data.fixture_difficulty_multiplier
