from __future__ import annotations

import datetime as dt
from typing import Annotated

from api.adapters.fpl import FplApiClient
from api.core.settings import get_settings
from api.db.session import get_db_session
from api.repositories import (
    FixtureRepository,
    GameweekRepository,
    PlayerRepository,
    PlayerSnapshotRepository,
    TeamRepository,
)
from api.services import IMPORT_STATUS_STORE, ImportFplDataService, ImportState, ImportStatusStore
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/imports/fpl", tags=["imports"])


class ImportSummaryResponse(BaseModel):
    teams_imported: int
    players_imported: int
    gameweeks_imported: int
    fixtures_imported: int
    player_snapshots_captured: int = 0


class ImportStatusResponse(BaseModel):
    state: str
    message: str | None
    last_run_started_at: dt.datetime | None
    last_run_finished_at: dt.datetime | None
    last_summary: ImportSummaryResponse | None


def get_import_status_store() -> ImportStatusStore:
    return IMPORT_STATUS_STORE


def get_import_service(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ImportFplDataService:
    settings = get_settings()
    provider = FplApiClient(base_url=settings.fpl_api_base_url)

    return ImportFplDataService(
        provider=provider,
        team_repository=TeamRepository(db_session),
        player_repository=PlayerRepository(db_session),
        gameweek_repository=GameweekRepository(db_session),
        fixture_repository=FixtureRepository(db_session),
        player_snapshot_repository=PlayerSnapshotRepository(db_session),
    )


ImportServiceDep = Annotated[ImportFplDataService, Depends(get_import_service)]
DbSessionDep = Annotated[Session, Depends(get_db_session)]
ImportStatusStoreDep = Annotated[ImportStatusStore, Depends(get_import_status_store)]


@router.post("/run", response_model=ImportSummaryResponse)
def run_import(
    service: ImportServiceDep,
    db_session: DbSessionDep,
    status_store: ImportStatusStoreDep,
) -> ImportSummaryResponse:
    now = dt.datetime.now(dt.UTC)
    status_store.status.state = ImportState.RUNNING
    status_store.status.last_run_started_at = now
    status_store.status.last_run_finished_at = None
    status_store.status.message = None

    try:
        summary = service.import_bootstrap_static()
        db_session.commit()
    except Exception as exc:
        db_session.rollback()
        status_store.status.state = ImportState.FAILED
        status_store.status.last_run_finished_at = dt.datetime.now(dt.UTC)
        status_store.status.message = str(exc)
        raise

    status_store.status.state = ImportState.SUCCEEDED
    status_store.status.last_run_finished_at = dt.datetime.now(dt.UTC)
    status_store.status.message = "Import completed"
    status_store.status.last_summary = summary

    return ImportSummaryResponse(
        teams_imported=summary.teams_imported,
        players_imported=summary.players_imported,
        gameweeks_imported=summary.gameweeks_imported,
        fixtures_imported=summary.fixtures_imported,
        player_snapshots_captured=summary.player_snapshots_captured,
    )


@router.get("/status", response_model=ImportStatusResponse)
def get_import_status(
    status_store: ImportStatusStoreDep,
) -> ImportStatusResponse:
    summary = status_store.status.last_summary
    mapped_summary: ImportSummaryResponse | None = None
    if summary is not None:
        mapped_summary = ImportSummaryResponse(
            teams_imported=summary.teams_imported,
            players_imported=summary.players_imported,
            gameweeks_imported=summary.gameweeks_imported,
            fixtures_imported=summary.fixtures_imported,
            player_snapshots_captured=summary.player_snapshots_captured,
        )

    return ImportStatusResponse(
        state=status_store.status.state.value,
        message=status_store.status.message,
        last_run_started_at=status_store.status.last_run_started_at,
        last_run_finished_at=status_store.status.last_run_finished_at,
        last_summary=mapped_summary,
    )
