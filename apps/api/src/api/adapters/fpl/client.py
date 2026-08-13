from __future__ import annotations

import httpx
from api.adapters.fpl.schemas import BootstrapStaticDto, EventLiveDto, FplFixtureDto
from api.core.exceptions import ExternalServiceError
from pydantic import ValidationError


class FplApiClient:
    def __init__(self, base_url: str = "https://fantasy.premierleague.com/api") -> None:
        self._base_url = base_url.rstrip("/")

    def fetch_bootstrap_static(self) -> BootstrapStaticDto:
        url = f"{self._base_url}/bootstrap-static/"
        try:
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Failed to fetch FPL bootstrap data from {url}") from exc

        try:
            return BootstrapStaticDto.model_validate(response.json())
        except ValidationError as exc:
            raise ExternalServiceError("FPL bootstrap payload schema validation failed") from exc

    def fetch_fixtures(self) -> list[FplFixtureDto]:
        url = f"{self._base_url}/fixtures/"
        try:
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Failed to fetch FPL fixtures data from {url}") from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise ExternalServiceError("FPL fixtures payload schema validation failed")

        try:
            return [FplFixtureDto.model_validate(item) for item in payload]
        except ValidationError as exc:
            raise ExternalServiceError("FPL fixtures payload schema validation failed") from exc

    def fetch_event_live(self, event_id: int) -> EventLiveDto:
        url = f"{self._base_url}/event/{event_id}/live/"
        try:
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Failed to fetch FPL live data from {url}") from exc

        try:
            return EventLiveDto.model_validate(response.json())
        except ValidationError as exc:
            raise ExternalServiceError("FPL live payload schema validation failed") from exc
