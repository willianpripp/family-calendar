# Telegram reminders for calendar events.
#
# Two per event, confirmed by Willian on 2026-08-08: one the day before, and one
# two hours before. Both are read from the event's own owner field and sent to
# that person's chat; "Both" goes to the two of them. There is no per-user
# identity anywhere in this app, so routing on the owner field is the only
# honest option, and it is what the rest of the app already does.
#
# Two interpretations worth stating, because "one day before" is ambiguous:
#
#   The day-before reminder fires at 18:00 local the previous evening, not at
#   the same clock time 24 hours earlier. A 07:00 flight should not wake anyone
#   at 07:00 the day before to say it exists.
#
#   The two-hour reminder fires exactly two hours before, including in the small
#   hours. At 05:00 for a 07:00 flight that is the entire point of it.
#
# An all-day event gets only the first: "two hours before" a birthday means
# nothing.
#
# Standalone reminders (item_kind='reminder', 2026-08-14) are the third shape:
# a to-do with a due date. They get neither of the above. Instead they nag at
# 09:00 every day, from the day they are created until someone presses OK in
# the calendar (acknowledged_at) — including past the due date, because the
# whole point of a nag is that missing the deadline does not silence it. The
# morning hour is deliberate: these are errands and paperwork, done in
# business hours, and an evening nag arrives after the day that could have
# absorbed it is gone.

import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta

API = "https://api.telegram.org/bot{token}/{method}"

# How often the loop wakes. Nothing here needs to be minute-accurate, and a
# reminder is allowed to be a few minutes late.
TICK_SECONDS = 300

# How late a reminder may be sent after its due time. This is the guard against
# the app coming back from an outage and firing a week of stale reminders at
# two phones at once. Past this, the moment has gone and silence is better.
GRACE = timedelta(hours=6)

# The evening before, in household local time.
DAY_BEFORE_AT = time(18, 0)

# When the daily nag for a standalone reminder goes out. Morning, so the day
# it interrupts is the day that can still do something about it.
NAG_AT = time(9, 0)


def _token() -> str:
    return os.environ.get("CAL_TELEGRAM_TOKEN", "").strip()


def chats() -> dict[str, int]:
    """CAL_TELEGRAM_CHATS="Willian=111111111,Aline=222222222".

    Keys match the event owner values exactly, so routing is a dictionary lookup
    rather than a mapping table nobody remembers to update.
    """
    out = {}
    for entry in os.environ.get("CAL_TELEGRAM_CHATS", "").split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        name, _, chat = entry.partition("=")
        try:
            out[name.strip()] = int(chat)
        except ValueError:
            continue
    return out


def configured() -> bool:
    return bool(_token()) and bool(chats())


def send(chat_id: int, text: str) -> bool:
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(API.format(token=_token(), method="sendMessage"), data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp).get("ok", False)
    except Exception:
        # A failed send must not take the loop down with it. The row is left
        # unmarked, so the next tick tries again until GRACE runs out.
        return False


def recipients(owner: str) -> list[int]:
    book = chats()
    if owner == "Both":
        return list(book.values())
    chat = book.get(owner)
    return [chat] if chat else []


def compose(ev: dict, kind: str, tz, now: datetime | None = None) -> str:
    """Deliberately almost no chrome.

    The event's own title carries the meaning and it is written in whichever
    language the household wrote it in. The chrome around it is English, like
    the app, since 2026-08-14 (Willian's item 3: it opened Portuguese and he
    asked for the switch the first time he read one).

    A nag opens with "Reminder:", his ask of the same day: the phone shows one
    line, and that line must already say whether this is something scheduled
    or something owed. Scheduled kinds carry no prefix, so the absence is the
    other half of the signal.
    """
    start = ev["starts_at"].astimezone(tz)
    if kind == "nag":
        due_day = start.date()
        today = now.astimezone(tz).date()
        if today == due_day:
            when = "Reminder: due today"
        elif today > due_day:
            when = f"Reminder: overdue since {due_day:%b %-d}"
        else:
            when = f"Reminder: due by {due_day:%b %-d}"
        lines = [when]
    else:
        when = "Tomorrow" if kind == "day" else "In 2 hours"
        # The same clock the app writes: 7:00pm, meridiem always present.
        at = f"{start:%-I:%M%p}".lower()
        lines = [f"{when}, {at}" if not ev["all_day"] else f"{when}"]
    # The enrichment, Willian's item 2 ("enriquecer legal msm"): the message
    # reads like the calendar entry. Sticker rides the title, then location,
    # notes (capped so an essay in the notes field stays an essay in the app,
    # not on the phone), then the category. Colour is the one thing that stays
    # behind: a plain-text Telegram message has nowhere to put it, and the
    # sticker plus category already carry the identity.
    sticker = (ev.get("sticker") or "").strip()
    lines.append(f"{sticker} {ev['title']}" if sticker else ev["title"])
    if ev.get("location"):
        lines.append(ev["location"])
    notes = (ev.get("notes") or "").strip()
    if notes:
        lines.append(notes if len(notes) <= 200 else notes[:200] + "…")
    if ev.get("category_name"):
        lines.append(ev["category_name"])
    if ev["owner"] == "Both":
        lines.append("(both of you)")
    return "\n".join(lines)


def due_at(ev: dict, kind: str, tz) -> datetime | None:
    """When this reminder should have gone out, or None if it does not apply."""
    start = ev["starts_at"].astimezone(tz)
    if kind == "day":
        # Always 18:00 the previous evening, full stop. The first version had a
        # "fall back to 24 hours earlier" special case for early events, which
        # was outsmarting itself: 18:00 the evening before is by construction
        # earlier than any time on the event's day, and the "fallback" turned a
        # 07:00 flight's reminder into a 07:00 wake-up and a birthday's into a
        # midnight one. Caught by the timing tests, not by rereading the code.
        return datetime.combine(start.date() - timedelta(days=1), DAY_BEFORE_AT, tzinfo=tz)
    if kind == "hour":
        return None if ev["all_day"] else start - timedelta(hours=2)
    return None


def pending(events: list[dict], already: set[tuple[int, str]], now: datetime, tz):
    """Yield (event, kind, stored_kind) for everything due and unsent.

    `stored_kind` is what goes in reminders_sent. For a yearly occurrence it
    carries the year ("day@2027"), because the same event id must remind again
    every year, and a bare (id, "day") row would suppress it forever after the
    first one.

    Standalone reminders get one "nag" per day instead, keyed by that day
    ("nag@2026-08-19"): the same per-occurrence idea as the yearly keys, at a
    daily grain. A reminder created after the nag hour plus grace simply
    starts tomorrow, with no special case: today's 09:00 is already outside
    the window by the time the row exists.
    """
    for ev in events:
        if ev.get("item_kind") == "reminder":
            if ev.get("acknowledged_at"):
                continue
            stored = f"nag@{now.astimezone(tz).date().isoformat()}"
            if (ev["id"], stored) in already:
                continue
            due = datetime.combine(now.astimezone(tz).date(), NAG_AT, tzinfo=tz)
            if due <= now <= due + GRACE:
                yield ev, "nag", stored
            continue
        for kind in ("day", "hour"):
            stored = f"{kind}@{ev['starts_at'].year}" if ev.get("occurrence") else kind
            if (ev["id"], stored) in already:
                continue
            due = due_at(ev, kind, tz)
            if due is None:
                continue
            if due <= now <= due + GRACE:
                yield ev, kind, stored
