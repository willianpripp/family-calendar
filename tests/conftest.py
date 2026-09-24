# The calendar's API tests run against a real Postgres (docker-compose.test.yml
# provides one) through FastAPI's TestClient, with the app module imported
# exactly as uvicorn imports it: from app/ as the working directory, because
# the templates and static mounts are relative paths.
#
# CAL_API_KEY is read once at import, so it is set before the import below.

import os
import pathlib
import sys

APP_DIR = pathlib.Path(__file__).parent.parent / "app"
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)
os.environ.setdefault("CAL_API_KEY", "test-api-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main as app_module  # noqa: E402

API_KEY = os.environ["CAL_API_KEY"]


@pytest.fixture(scope="session")
def _session_client():
    # client=("127.0.0.1", ...) replaces the TestClient's placeholder peer
    # ("testclient", not an IP), which gate.py would read as untrusted; the
    # real app only ever sees its loopback-bound proxy as the TCP peer.
    with TestClient(app_module.app, client=("127.0.0.1", 12345)) as c:
        yield c


@pytest.fixture
def client(_session_client):
    _session_client.cookies.clear()
    return _session_client


@pytest.fixture(autouse=True)
def _clean_db(_session_client):
    with app_module.pool.connection() as conn:
        conn.execute("truncate events, reminders_sent restart identity cascade")
    yield


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {API_KEY}"}
