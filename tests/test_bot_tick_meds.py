# bot_tick's routing for a `meds:*` callback: it must be checked against the
# CAL_TELEGRAM_CHATS allowlist same as any other callback, forwarded to meds
# (or answered "Not available" without forwarding, if the env isn't
# configured or the chat isn't known), answered with whatever toast comes
# back, and never fall through into the ack/later handling below it or have
# its buttons stripped the way ack/later's own do (meds edits its own
# messages once the dose is recorded).
#
# Drives the real bot_tick against a real Postgres (see tests/conftest.py)
# and local fake Telegram + fake meds HTTP servers — no real bot, no real
# meds instance.

import http.server
import json
import threading
import urllib.parse

import pytest

import main as app_module
import reminders


class _TelegramHandler(http.server.BaseHTTPRequestHandler):
    server_version = "FakeTelegram/1"

    def log_message(self, fmt, *args):  # keep pytest -q output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        params = dict(urllib.parse.parse_qsl(body.decode()))
        method = self.path.rsplit("/", 1)[-1]
        state: FakeTelegram = self.server.state
        state.calls.append({"method": method, "params": params})
        if method == "getUpdates":
            result = state.next_batch
        else:
            result = True
        payload = json.dumps({"ok": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class FakeTelegram:
    def __init__(self):
        self.calls: list[dict] = []
        self.next_batch: list[dict] = []

    def calls_for(self, method: str) -> list[dict]:
        return [c["params"] for c in self.calls if c["method"] == method]


@pytest.fixture
def fake_telegram(monkeypatch):
    state = FakeTelegram()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _TelegramHandler)
    httpd.state = state
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    # reminders.API is a plain module-level format string ("…/bot{token}/
    # {method}"); pointing it at the fake server is simpler and less
    # invasive than adding a whole new env-driven override just for tests.
    monkeypatch.setattr(reminders, "API", f"http://127.0.0.1:{port}/bot{{token}}/{{method}}")
    monkeypatch.setenv("CAL_TELEGRAM_TOKEN", "test-token")
    yield state
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


class _MedsHandler(http.server.BaseHTTPRequestHandler):
    server_version = "FakeMeds/1"

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode() or "{}")
        state: FakeMeds = self.server.state
        state.requests.append(body)
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


@pytest.fixture
def fake_meds(monkeypatch):
    state = FakeMeds()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MedsHandler)
    httpd.state = state
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    monkeypatch.setenv("CAL_MEDS_CALLBACK_URL", f"http://127.0.0.1:{port}/api/telegram/callback")
    monkeypatch.setenv("CAL_MEDS_CALLBACK_KEY", "test-callback-key")
    yield state
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _callback_update(chat_id, data, message_id=555, from_id=999, update_id=1, callback_id="cb1"):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_id,
            "from": {"id": from_id},
            "message": {"message_id": message_id, "chat": {"id": chat_id}},
            "data": data,
        },
    }


def test_meds_callback_forwarded_after_allowlist_and_buttons_not_stripped(
    calendar_db, fake_telegram, fake_meds, monkeypatch,
):
    monkeypatch.setenv("CAL_TELEGRAM_CHATS", "Willian=100,Aline=200")
    fake_telegram.next_batch = [_callback_update(100, "meds:give:5-1758654000")]

    acked = app_module.bot_tick()

    assert acked == 0  # a meds: press is never an ack on the calendar's side
    assert fake_meds.requests == [
        {"chat_id": 100, "from_id": 999, "message_id": 555, "data": "meds:give:5-1758654000"},
    ]
    answers = fake_telegram.calls_for("answerCallbackQuery")
    assert len(answers) == 1
    assert answers[0]["text"] == fake_meds.toast
    # meds edits its own messages; this app must never strip its buttons.
    assert fake_telegram.calls_for("editMessageReplyMarkup") == []


def test_meds_callback_from_unknown_chat_is_answered_not_silently_dropped(
    calendar_db, fake_telegram, fake_meds, monkeypatch,
):
    monkeypatch.setenv("CAL_TELEGRAM_CHATS", "Willian=100,Aline=200")
    fake_telegram.next_batch = [_callback_update(999999999, "meds:give:5-1758654000")]

    app_module.bot_tick()

    assert fake_meds.requests == []  # never forwarded: the chat isn't allowlisted
    answers = fake_telegram.calls_for("answerCallbackQuery")
    assert len(answers) == 1
    assert answers[0]["text"] == "Not available."


def test_meds_callback_with_env_unset_answers_not_available(
    calendar_db, fake_telegram, monkeypatch,
):
    monkeypatch.setenv("CAL_TELEGRAM_CHATS", "Willian=100,Aline=200")
    monkeypatch.delenv("CAL_MEDS_CALLBACK_URL", raising=False)
    monkeypatch.delenv("CAL_MEDS_CALLBACK_KEY", raising=False)
    fake_telegram.next_batch = [_callback_update(100, "meds:give:5-1758654000")]

    app_module.bot_tick()

    answers = fake_telegram.calls_for("answerCallbackQuery")
    assert len(answers) == 1
    assert answers[0]["text"] == "Not available."


def test_meds_callback_never_falls_through_to_ack_later(
    calendar_db, fake_telegram, fake_meds, monkeypatch,
):
    """A "meds:give:<n>" payload, split the way ack/later's own parser
    splits data, would land on action "meds" — not "ack" or "later" — and
    be silently ignored there too, so a bug that let it fall through
    wouldn't crash; it just wouldn't answer the press at all. The real
    regression this guards is that exactly one answer goes out, from the
    meds branch, per update — never zero and never two."""
    monkeypatch.setenv("CAL_TELEGRAM_CHATS", "Willian=100,Aline=200")
    fake_telegram.next_batch = [_callback_update(100, "meds:give:5-1758654000")]

    app_module.bot_tick()

    assert len(fake_telegram.calls_for("answerCallbackQuery")) == 1


def test_ack_callback_is_unaffected_by_the_meds_branch(
    calendar_db, fake_telegram, monkeypatch,
):
    """A sanity check that adding the meds: branch didn't disturb the
    existing ack path: a real "ack:<id>" press still acknowledges and still
    strips its own message's buttons."""
    monkeypatch.setenv("CAL_TELEGRAM_CHATS", "Willian=100,Aline=200")
    with app_module.pool.connection() as conn:
        row = conn.execute(
            "insert into events (title, starts_at, ends_at, all_day, owner, item_kind) "
            "values ('Renew passport', now(), now() + interval '1 day', true, 'Willian', "
            "'reminder') returning id"
        ).fetchone()
    event_id = row["id"]
    fake_telegram.next_batch = [_callback_update(100, f"ack:{event_id}")]

    acked = app_module.bot_tick()

    assert acked == 1
    assert fake_telegram.calls_for("answerCallbackQuery")[0]["text"] == "Done ✓"
    assert len(fake_telegram.calls_for("editMessageReplyMarkup")) == 1
