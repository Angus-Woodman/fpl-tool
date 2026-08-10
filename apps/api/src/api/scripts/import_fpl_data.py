from __future__ import annotations

import logging

from api.adapters.fpl import FplApiClient
from api.core.logging import configure_logging
from api.core.settings import get_settings
from api.db.session import SessionLocal
from api.repositories import FixtureRepository, GameweekRepository, PlayerRepository, TeamRepository
from api.services import ImportFplDataService


def main() -> None:
    configure_logging()
    logger = logging.getLogger("api.import_fpl_data")

    settings = get_settings()
    base_url = settings.fpl_api_base_url

    with SessionLocal() as session:
        service = ImportFplDataService(
            provider=FplApiClient(base_url=base_url),
            team_repository=TeamRepository(session),
            player_repository=PlayerRepository(session),
            gameweek_repository=GameweekRepository(session),
            fixture_repository=FixtureRepository(session),
        )

        summary = service.import_bootstrap_static()
        session.commit()

    logger.info(
        "FPL bootstrap import completed",
        extra={
            "teams_imported": summary.teams_imported,
            "players_imported": summary.players_imported,
            "gameweeks_imported": summary.gameweeks_imported,
            "fixtures_imported": summary.fixtures_imported,
            "fpl_api_base_url": base_url,
        },
    )


if __name__ == "__main__":
    main()
