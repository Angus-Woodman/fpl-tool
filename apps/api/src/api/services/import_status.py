from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum

from api.services.import_fpl_data import ImportSummary


class ImportState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class ImportStatus:
    state: ImportState = ImportState.IDLE
    last_run_started_at: dt.datetime | None = None
    last_run_finished_at: dt.datetime | None = None
    message: str | None = None
    last_summary: ImportSummary | None = None


@dataclass
class ImportStatusStore:
    status: ImportStatus = field(default_factory=ImportStatus)


IMPORT_STATUS_STORE = ImportStatusStore()
