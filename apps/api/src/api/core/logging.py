import logging

from api.core.settings import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.api_log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
