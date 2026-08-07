from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_history_has_exactly_one_head() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(backend_dir / "alembic.ini")
    config.set_main_option(
        "script_location",
        str(backend_dir / "migrations"),
    )

    heads = ScriptDirectory.from_config(config).get_heads()

    assert heads == ["20260807_0047"]
