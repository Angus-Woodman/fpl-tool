from collections.abc import Generator

from api.core.settings import get_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
