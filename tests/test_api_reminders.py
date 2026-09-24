# The reminder API another household app uses: POST creates a to-do that the
# bot nags about, keyed by the caller's external_id; DELETE with the same
# external_id removes it again so a to-do that stopped being true stops
# nagging.

import pytest

import main as app_module


@pytest.fixture(autouse=True)
def _clean(calendar_db):
    """Every test here starts from empty events/reminders_sent (conftest's
    calendar_db, shared with the bot_tick tests)."""
    yield


def _create(client, auth, external_id="meds-vaccine-1-2026-10-01", **extra):
    body = {"title": "Pixel: Rabies vaccine due", "due_date": "2026-10-01",
            "owner": "Both", "lead_days": 14, "external_id": external_id}
    body.update(extra)
    return client.post("/api/reminders", json=body, headers=auth)


def _count(sql, params=()):
    with app_module.pool.connection() as conn:
        return conn.execute(sql, params).fetchone()["n"]


def test_create_then_repeat_with_same_external_id_returns_the_same_row(client, auth):
    first = _create(client, auth)
    again = _create(client, auth)
    assert first.status_code == 200 and first.json()["created"] is True
    assert again.json() == {"id": first.json()["id"], "created": False}
    assert _count("select count(*) as n from events") == 1


def test_delete_by_external_id_removes_the_reminder_and_its_sent_history(client, auth):
    rid = _create(client, auth).json()["id"]
    with app_module.pool.connection() as conn:
        conn.execute("insert into reminders_sent (event_id, kind) values (%s, 'nag@2026-09-20')",
                     (rid,))
    resp = client.delete("/api/reminders", params={"external_id": "meds-vaccine-1-2026-10-01"},
                         headers=auth)
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    assert _count("select count(*) as n from events") == 0
    assert _count("select count(*) as n from reminders_sent") == 0


def test_delete_is_idempotent_for_a_retry_after_a_lost_response(client, auth):
    _create(client, auth)
    params = {"external_id": "meds-vaccine-1-2026-10-01"}
    assert client.delete("/api/reminders", params=params, headers=auth).json() == {"deleted": True}
    again = client.delete("/api/reminders", params=params, headers=auth)
    assert again.status_code == 200
    assert again.json() == {"deleted": False}


def test_delete_touches_only_the_matching_api_reminder(client, auth):
    _create(client, auth, external_id="keep-me")
    _create(client, auth, external_id="drop-me")
    with app_module.pool.connection() as conn:
        # A form-made event and a form-made reminder: no external_id at all.
        conn.execute(
            "insert into events (title, starts_at, ends_at, all_day, owner, item_kind)"
            " values ('Dentist', now(), now() + interval '1 hour', false, 'Both', 'event'),"
            " ('Renew passport', now(), now() + interval '1 day', true, 'Both', 'reminder')"
        )
    client.delete("/api/reminders", params={"external_id": "drop-me"}, headers=auth)
    with app_module.pool.connection() as conn:
        left = {r["title"] if r["external_id"] is None else r["external_id"]
                for r in conn.execute("select title, external_id from events").fetchall()}
    assert left == {"keep-me", "Dentist", "Renew passport"}


def test_delete_never_reaches_a_non_reminder_row_with_an_external_id(client, auth):
    with app_module.pool.connection() as conn:
        conn.execute(
            "insert into events (title, starts_at, ends_at, all_day, owner, item_kind, external_id)"
            " values ('Flight', now(), now() + interval '2 hours', false, 'Both', 'event', 'ev-1')"
        )
    resp = client.delete("/api/reminders", params={"external_id": "ev-1"}, headers=auth)
    assert resp.json() == {"deleted": False}
    assert _count("select count(*) as n from events") == 1


def test_delete_requires_the_bearer_key(client, auth):
    _create(client, auth)
    params = {"external_id": "meds-vaccine-1-2026-10-01"}
    assert client.delete("/api/reminders", params=params).status_code == 401
    wrong = {"Authorization": "Bearer not-the-key"}
    assert client.delete("/api/reminders", params=params, headers=wrong).status_code == 401
    assert _count("select count(*) as n from events") == 1


def test_delete_is_off_not_open_when_the_key_is_unset(client, auth, monkeypatch):
    monkeypatch.setattr(app_module, "CAL_API_KEY", "")
    resp = client.delete("/api/reminders", params={"external_id": "x"}, headers=auth)
    assert resp.status_code == 503


def test_delete_rejects_a_blank_external_id(client, auth):
    _create(client, auth)
    resp = client.delete("/api/reminders", params={"external_id": "  "}, headers=auth)
    assert resp.status_code == 422
    assert _count("select count(*) as n from events") == 1


def test_delete_is_reachable_without_a_login_from_a_public_address(client, auth):
    # front_door exempts /api/reminders by path, so the DELETE must answer
    # with its own auth result, never a redirect to the login page.
    public = {"X-Forwarded-For": "203.0.113.9"}
    resp = client.delete("/api/reminders", params={"external_id": "x"},
                         headers=public, follow_redirects=False)
    assert resp.status_code == 401
