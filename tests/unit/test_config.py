from app.core.config import Settings


def test_comma_separated_cors_origins_are_supported() -> None:
    settings = Settings(cors_allowed_origins="http://one.test,http://two.test")
    assert settings.cors_allowed_origins == ["http://one.test", "http://two.test"]
