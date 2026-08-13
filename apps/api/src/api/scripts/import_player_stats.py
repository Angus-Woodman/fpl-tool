from __future__ import annotations

import logging

from api.adapters.fpl import FplApiClient
from api.core.logging import configure_logging
from api.core.settings import get_settings
from api.db.session import SessionLocal
from api.repositories import (
    GameweekRepository,
    PlayerGameweekStatRepository,
    PlayerRepository,
)
from api.services import ImportPlayerStatsService


def main() -> None:
    configure_logging()
    logger = logging.getLogger("api.import_player_stats")

    settings = get_settings()
    base_url = settings.fpl_api_base_url

    with SessionLocal() as session:
        service = ImportPlayerStatsService(
            provider=FplApiClient(base_url=base_url),
            gameweek_repository=GameweekRepository(session),
            player_repository=PlayerRepository(session),
            stat_repository=PlayerGameweekStatRepository(session),
        )

        summary = service.import_finished_gameweeks()
        session.commit()

    logger.info(
        "FPL results import completed",
        extra={
            "gameweeks_imported": summary.gameweeks_imported,
            "stats_imported": summary.stats_imported,
            "fpl_api_base_url": base_url,
        },
    )


if __name__ == "__main__":
    main()
