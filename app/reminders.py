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

import colorsys
import html
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


def _call(method: str, _timeout: int = 20, **params):
    """One Telegram method call; None on any failure, never an exception.

    Everything here follows send()'s original rule: the bot must not be able
    to take the app down, so the network is allowed to fail quietly and the
    caller decides what quiet failure means.
    """
    data = urllib.parse.urlencode(params).encode()
    try:
        req = urllib.request.Request(API.format(token=_token(), method=method), data=data)
        with urllib.request.urlopen(req, timeout=_timeout) as resp:
            out = json.load(resp)
            return out.get("result") if out.get("ok") else None
    except Exception:
        return None


def send(chat_id: int, text: str, buttons: list | None = None) -> bool:
    # HTML parse mode carries the bold first line compose() writes. Everything
    # user-written in the message is escaped there; a title containing "<3"
    # must never be able to break its own reminder. `buttons` is a Telegram
    # inline keyboard; the nags carry their Done button through it.
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if buttons:
        params["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    # A failed send is False, the row stays unmarked, the next tick retries
    # until GRACE runs out.
    return _call("sendMessage", **params) is not None


# Long polling: getUpdates holds the connection open until something arrives
# or LONG_POLL seconds pass, so a Done press lands in ~2 seconds. That speed
# is not cosmetic: Telegram expires a button press's little "Done ✓" toast
# about 30 seconds after the finger, and a poller on a 60-second interval
# answered into the void, which read as "nothing happened" on the phone
# (learned live, 2026-08-14). The person who just pressed is looking at the
# screen; the reminder tick can be minutes late, this cannot.
LONG_POLL = 50


def updates(offset: int):
    """New updates, held open up to LONG_POLL seconds; None if unreachable."""
    return _call("getUpdates", _timeout=LONG_POLL + 10, offset=offset, timeout=LONG_POLL)


def answer_callback(callback_id: str, text: str) -> None:
    _call("answerCallbackQuery", callback_query_id=callback_id, text=text)


def strip_buttons(chat_id: int, message_id: int) -> None:
    """Remove the inline keyboard from a sent message, so a pressed Done
    cannot be pressed again tomorrow on a stale message."""
    _call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
          reply_markup=json.dumps({"inline_keyboard": []}))


def recipients(owner: str) -> list[int]:
    book = chats()
    if owner == "Both":
        return list(book.values())
    chat = book.get(owner)
    return [chat] if chat else []


def swatch(hex_color: str) -> str:
    """The category's colour as the nearest emoji square.

    Telegram has no coloured text, full stop; a coloured square is the whole
    vocabulary. Matched by hue rather than by a table of the palette, because
    category colours come from a free colour picker and any hex can arrive.
    """
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return ""
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return ""
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.15:
        return "⬜" if light > 0.5 else "⬛"
    deg = hue * 360
    if deg < 12 or deg >= 335:
        return "🟥"
    if deg < 40:
        return "🟧"
    if deg < 65:
        return "🟨"
    if deg < 160:
        return "🟩"
    if deg < 260:
        return "🟦"
    return "🟪"


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
        # The first word says what kind of thing this is, Willian's ask: a
        # timed entry is an appointment, a whole-day one is an event, and the
        # reminder branch above already opens with "Reminder:".
        what = "Event" if ev["all_day"] else "Appointment"
        when = "tomorrow" if kind == "day" else "in 2 hours"
        # The same clock the app writes: 7:00pm, meridiem always present.
        at = f"{start:%-I:%M%p}".lower()
        lines = [f"{what} {when}, {at}" if not ev["all_day"] else f"{what} {when}"]
    # The enrichment, Willian's item 2 ("enriquecer legal msm"), with each
    # field named so nobody has to guess which line is which. Notes are capped
    # so an essay in the notes field stays an essay in the app, not on the
    # phone. Colour is the one field left behind: a plain-text Telegram
    # message has nowhere to put it, and the sticker plus category already
    # carry the identity.
    # The first line is bold (Willian, 2026-08-14) and send() speaks HTML for
    # it, so every user-written field below is escaped: a "<3" in a title must
    # never eat its own reminder.
    lines[0] = f"<b>{lines[0]}</b>"
    sticker = (ev.get("sticker") or "").strip()
    title = html.escape(ev["title"])
    lines.append(f"{sticker} {title}" if sticker else title)
    if ev.get("location"):
        lines.append(f"Location: {html.escape(ev['location'])}")
    notes = (ev.get("notes") or "").strip()
    if notes:
        lines.append(f"Notes: {html.escape(notes if len(notes) <= 200 else notes[:200] + '…')}")
    if ev.get("category_name"):
        sq = swatch(ev.get("category_color") or "")
        lines.append(f"Category: {sq} {html.escape(ev['category_name'])}".replace("  ", " "))
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
