# Makes app/ importable (import main, import reminders) the same way
# uvicorn sees it in production. DB-backed fixtures live here for
# tests/test_bot_tick_meds.py only — tests/test_meds_forward.py needs none
# of this (forward_meds_callback is pure) and never requests them, so it
# stays exactly as cheap to run as before.

import os
import pathlib
import sys

APP_DIR = pathlib.Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# CAL_API_KEY is read once when main is imported; docker-compose.test.yml
# sets it, and this default keeps a bare local run from importing main with
# the reminder API switched off.
os.environ.setdefault("CAL_API_KEY", "test-api-key")

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


@pytest.fixture(scope="session")
def _session_client(_db_ready):
    """A TestClient for the HTTP API tests (tests/test_api_reminders.py),
    entered once so the app's lifespan runs a single time. client=("127.0.0.1",
    ...) replaces the TestClient's placeholder peer ("testclient", not an
    IP), which gate.py would read as untrusted; production only ever sees its
    loopback-bound proxy as the TCP peer."""
    from fastapi.testclient import TestClient
    with TestClient(_db_ready.app, client=("127.0.0.1", 12345)) as c:
        yield c


@pytest.fixture
def client(_session_client):
    _session_client.cookies.clear()
    return _session_client


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {os.environ['CAL_API_KEY']}"}
