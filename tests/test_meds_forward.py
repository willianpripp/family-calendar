# app/reminders.forward_meds_callback against a local fake HTTP server: no
# real bot, no real meds instance, no database. This repo has no other
# automated test suite; this file exists specifically because
# forward_meds_callback was written as a pure function (URL and key passed
# in, nothing read from the environment) so it could be tested exactly like
# this — see its own docstring in app/reminders.py.

import http.server
import json
import pathlib
import sys
import threading

import pytest

APP_DIR = pathlib.Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reminders  # noqa: E402  (path insert must happen first)


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "FakeMeds/1"

    def log_message(self, fmt, *args):  # keep pytest -q output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode() or "{}")
        state: FakeMeds = self.server.state
        state.requests.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "body": body,
        })
        if state.status != 200:
            payload = json.dumps({"error": "boom"}).encode()
            self.send_response(state.status)
        else:
            payload = json.dumps({"toast": state.toast}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class FakeMeds:
    def __init__(self):
        self.requests: list[dict] = []
        self.toast = "Given – Pixel's 19:00 dose."
        self.status = 200


@pytest.fixture
def fake_meds():
    state = FakeMeds()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.state = state
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{httpd.server_address[1]}/api/telegram/callback"
    yield state
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_forwards_the_body_and_the_bearer_key(fake_meds):
    toast = reminders.forward_meds_callback(
        fake_meds.url, "secret-key", 111, 222, 333, "meds:give:5-1758654000",
    )

    assert toast == fake_meds.toast
    assert len(fake_meds.requests) == 1
    req = fake_meds.requests[0]
    assert req["authorization"] == "Bearer secret-key"
    assert req["body"] == {
        "chat_id": 111, "from_id": 222, "message_id": 333, "data": "meds:give:5-1758654000",
    }


def test_from_id_can_be_omitted(fake_meds):
    reminders.forward_meds_callback(fake_meds.url, "k", 111, None, 333, "meds:snooze:5-1")
    assert fake_meds.requests[0]["body"]["from_id"] is None


def test_falls_back_to_not_available_when_meds_sends_no_toast(fake_meds):
    fake_meds.toast = None
    toast = reminders.forward_meds_callback(fake_meds.url, "k", 1, 1, 1, "meds:give:1-1")
    assert toast == "Not available."


def test_meds_error_response_returns_the_unreachable_toast(fake_meds):
    fake_meds.status = 500
    toast = reminders.forward_meds_callback(fake_meds.url, "k", 1, 1, 1, "meds:give:1-1")
    assert toast == "Meds is not reachable. Mark it in the app."


def test_unreachable_meds_returns_the_same_fallback_toast():
    # Port 1 is privileged and nothing is listening on it in CI or locally:
    # the connection is refused immediately, no timeout wait needed.
    toast = reminders.forward_meds_callback(
        "http://127.0.0.1:1/api/telegram/callback", "k", 1, 1, 1, "meds:give:1-1", timeout=1,
    )
    assert toast == "Meds is not reachable. Mark it in the app."


def test_meds_forward_configured_needs_both_env_vars(monkeypatch):
    monkeypatch.delenv("CAL_MEDS_CALLBACK_URL", raising=False)
    monkeypatch.delenv("CAL_MEDS_CALLBACK_KEY", raising=False)
    assert reminders.meds_forward_configured() is False

    monkeypatch.setenv("CAL_MEDS_CALLBACK_URL", "http://192.0.2.20:3050/api/telegram/callback")
    assert reminders.meds_forward_configured() is False  # key still unset

    monkeypatch.setenv("CAL_MEDS_CALLBACK_KEY", "k")
    assert reminders.meds_forward_configured() is True
