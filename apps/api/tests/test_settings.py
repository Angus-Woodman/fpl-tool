from api.core.settings import Settings


def test_settings_default_values() -> None:
    settings = Settings()

    assert settings.app_env in {"development", "test"}
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_test_database_url_is_optional_and_separate_from_the_development_url() -> None:
    settings = Settings(DATABASE_URL="postgresql+psycopg://fpl:fpl@localhost:5432/fpl")

    assert settings.test_database_url != settings.database_url
