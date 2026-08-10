from api.core.settings import Settings


def test_settings_default_values() -> None:
    settings = Settings()

    assert settings.app_env in {"development", "test"}
    assert settings.database_url.startswith("postgresql+psycopg://")
