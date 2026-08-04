"""Bring the Docker PostgreSQL database to the current Alembic revision."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db.session import engine


LEGACY_BASELINE_REVISION = "20260728_0006"
LEGACY_BASELINE_TABLES = {
    "audit_events",
    "auth_sessions",
    "entitlements",
    "favorites",
    "marketplace_plan_versions",
    "marketplace_plans",
    "order_items",
    "orders",
    "payment_events",
    "payments",
    "place_region_catalog_state",
    "place_region_snapshots",
    "places",
    "reports",
    "reviews",
    "user_must_place",
    "users",
}


def main() -> None:
    config = Config("alembic.ini")
    table_names = set(inspect(engine).get_table_names())

    # Older Docker builds used SQLAlchemy create_all() and therefore have the
    # full 0006-era schema without an Alembic version table. Preserve their
    # data, establish the correct baseline, then apply later migrations.
    if table_names and "alembic_version" not in table_names:
        missing_tables = LEGACY_BASELINE_TABLES - table_names
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise RuntimeError(
                "PostgreSQL schema has no Alembic version and is incomplete; "
                f"refusing to guess a baseline. Missing tables: {missing}"
            )
        command.stamp(config, LEGACY_BASELINE_REVISION)

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
