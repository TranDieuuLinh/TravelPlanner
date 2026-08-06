import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_accept_dedicated_application_database() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://vsf:vsf@postgres:5432/vsf_travel",
    )

    assert settings.database_url.endswith("/vsf_travel")
    assert settings.gemini_price_model == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("database_name", ["postgres", "POSTGRES"])
def test_settings_reject_postgres_maintenance_database(
    database_name: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="must not use the PostgreSQL maintenance database 'postgres'",
    ):
        Settings(
            _env_file=None,
            database_url=(
                "postgresql+psycopg://vsf:vsf@postgres:5432/"
                f"{database_name}"
            ),
        )
