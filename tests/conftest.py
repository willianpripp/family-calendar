# Makes app/ importable (import main, import reminders) the same way
# uvicorn sees it in production. DB-backed fixtures live here for
# tests/test_bot_tick_meds.py only — tests/test_meds_forward.py needs none
# of this (forward_meds_callback is pure) and never requests them, so it
# stays exactly as cheap to run as before.

import pathlib
import sys

APP_DIR = pathlib.Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pytest


@pytest.fixture(scope="session")
def _db_ready():
    """Opens the real connection pool and applies the schema once per test
    session — DATABASE_URL must already be set (docker-compose.test.yml's
    `tests` service sets it) since main.py reads it at import time."""
    import main as app_module
    if app_module.pool.closed:
        app_module.pool.open()
    with app_module.pool.connection() as conn:
        conn.execute(app_module.SCHEMA)
    yield app_module


@pytest.fixture
def calendar_db(_db_ready):
    """A clean slate for one test: every table bot_tick could touch,
    truncated, with bot_state's singleton row reset to offset 0 rather than
    truncated away (the schema only ever inserts it once, on `create table`,
    so a truncate would leave it missing for the rest of the session)."""
    app_module = _db_ready
    with app_module.pool.connection() as conn:
        conn.execute(
            "truncate events, reminders_sent, bot_dispatch restart identity cascade"
        )
        conn.execute("update bot_state set update_offset = 0 where id = 1")
    return app_module
