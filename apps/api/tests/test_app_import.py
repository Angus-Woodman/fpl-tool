from api.main import app


def test_app_title() -> None:
    assert app.title == "FPL Tool API"
