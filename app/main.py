# The family calendar. Deliberately small: one module of routes, no ORM, no
# migration framework. The schema is applied idempotently at startup, which is
# the right size of machinery for two tables and two people.
#
# The two design points that matter more than they look (see homelab STATUS):
#
#   Timezone. Storage is timestamptz (UTC); every parse and every render goes
#   through HOUSEHOLD_TZ explicitly. Form input arrives as naive local
#   wall-clock time and is localized here, never trusted as UTC. A calendar
#   silently four hours out is worse than none.
#
#   Ownership is an explicit field. Every family device signs in as the same
#   Tailscale account, so no identity header can tell one of us from the other.
#   The event says whose it is; the infrastructure cannot. The device address
#   *can* (see people.py), but that is used only to choose a background picture
#   and must never be given a job where being wrong matters.

import asyncio
import os
import time as systime
from calendar import Calendar
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

import gate
import news
import reminders
from art import (ACCEPT_ATTR, MAX_UPLOAD_BYTES, ArtError, art_for,
                 remove_month_art, save_month_art)
from people import PEOPLE, whois
from holidays import holidays_between

HOUSEHOLD_TZ = ZoneInfo(os.environ.get("CAL_TZ", "America/New_York"))
OWNERS = ("Willian", "Aline", "Both")

# The swatch set for categories. Picked to stay distinguishable against the
# dark ground AND against each other for the most common form of colour
# blindness, which rules out the red/green pair most palettes lean on.
PALETTE = [
    ("#4F86E5", "Blue"), ("#6EC1E4", "Sky"), ("#4FBF73", "Green"),
    ("#8FD35D", "Lime"), ("#E8C33D", "Yellow"), ("#F0A93D", "Amber"),
    ("#E5714D", "Orange"), ("#E5484D", "Red"), ("#E0679E", "Pink"),
    ("#B57BE0", "Purple"), ("#7A82E0", "Indigo"), ("#3FBFAF", "Teal"),
    ("#A98D6B", "Sand"), ("#8A94A6", "Slate"),
]

STICKERS = [
    "\U0001F389", "\U0001F382", "\U0001F381", "✈️", "\U0001F3D6️",
    "\U0001F3AC", "\U0001F3B8", "\U0001F3AB", "⚽", "\U0001F3C3",
    "\U0001F9D8", "\U0001F4AA", "\U0001F469‍⚕️", "\U0001F9B7",
    "\U0001F697", "\U0001F6E0️", "\U0001F4B0", "\U0001F4C8", "\U0001F4BB",
    "\U0001F4DA", "\U0001F374", "\U0001F355", "☕", "\U0001F37B",
    "\U0001F415", "\U0001F431", "❤️", "⭐", "❗", "\U0001F634",
]

SCHEMA = """
create table if not exists categories (
  id bigint generated always as identity primary key,
  name text not null unique,
  color text not null,
  sort_order int not null default 100
);

create table if not exists events (
  id bigint generated always as identity primary key,
  title text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  all_day boolean not null default false,
  owner text not null check (owner in ('Willian','Aline','Both')),
  location text not null default '',
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (ends_at > starts_at)
);
create index if not exists events_starts_at_idx on events (starts_at);

-- Added after the first release; `if not exists` keeps startup idempotent on
-- an existing database, which is the whole migration story this app needs.
alter table events add column if not exists category_id bigint
  references categories(id) on delete set null;
alter table events add column if not exists sticker text not null default '';

-- Yearly repetition, scoped to birthdays and anniversaries by Willian's
-- decision of 2026-08-08 (bills and rent live in the finances app). This is a
-- boolean, not an RRULE column: the household has exactly one recurrence
-- pattern, and general recurrence machinery for it would be all cost.
alter table events add column if not exists repeats_yearly boolean not null default false;

-- Standalone reminders, Willian's order of 2026-08-14: to-dos with a due date
-- ("matricula until the 19th"), not appointments with an hour. They reuse the
-- events table because every view and the reminder loop already know how to
-- carry an all-day row; a second table would mean a second copy of all of it.
-- acknowledged_at is the nag's off switch: null means still owed, and the
-- 09:00 daily nag keeps coming (even past the due date) until it is set.
alter table events add column if not exists item_kind text not null default 'event'
  check (item_kind in ('event','reminder'));
alter table events add column if not exists acknowledged_at timestamptz;

-- One row per reminder actually delivered, so a restart cannot send it twice.
-- `on delete cascade` because a deleted event should take its history with it,
-- and because without it a re-used id could inherit someone else's reminders.
create table if not exists reminders_sent (
  event_id bigint not null references events(id) on delete cascade,
  kind text not null,
  sent_at timestamptz not null default now(),
  primary key (event_id, kind)
);

-- Where the Telegram poller keeps its place in the update stream (the Done
-- button, 2026-08-14). One row, one number: the next update id to ask for.
-- In the database rather than in memory so a restart cannot replay presses.
create table if not exists bot_state (
  id int primary key,
  update_offset bigint not null default 0
);
insert into bot_state (id) values (1) on conflict do nothing;
"""

SEED_CATEGORIES = [
    ("Family", "#E0679E", 10),
    ("Work", "#4F86E5", 20),
    ("Travel", "#3FBFAF", 30),
    ("Health", "#4FBF73", 40),
    ("Fun", "#F0A93D", 50),
    ("Bills", "#8A94A6", 60),
]

pool = ConnectionPool(
    os.environ["DATABASE_URL"],
    min_size=1,
    max_size=4,
    kwargs={"row_factory": dict_row},
    open=False,
)


def reminder_tick() -> int:
    """One pass: find what is due, send it, record it. Returns messages sent.

    Synchronous and short. It is run in a thread from the loop below because the
    connection pool is psycopg's blocking one, and a blocking call on the event
    loop would stall every page render for the duration.
    """
    if not reminders.configured():
        return 0
    now = datetime.now(HOUSEHOLD_TZ)
    # Wide enough to cover both reminder kinds plus the grace window, narrow
    # enough that this never walks the whole table.
    window_end = now + timedelta(days=1, hours=2)
    sent = 0
    window_start = now - reminders.GRACE - timedelta(days=1)
    with pool.connection() as conn:
        rows = conn.execute(
            EVENT_SELECT + " where e.starts_at > %s and e.starts_at < %s"
            " and not e.repeats_yearly and e.item_kind = 'event'",
            (window_start, window_end),
        ).fetchall()
        # A birthday stored in 1990 never matches a date window, so the yearly
        # events are fetched whole and projected into it, exactly as the views
        # do. The projected rows carry occurrence=True, which is what makes
        # pending() key their sent-record by year: next year must remind again.
        yearly = conn.execute(EVENT_SELECT + " where e.repeats_yearly").fetchall()
        # Open reminders are fetched with no date window at all: an overdue
        # to-do keeps nagging however far past its due date it drifts, and a
        # starts_at window is exactly the thing that would silence it. They are
        # also excluded from the windowed query above, or a to-do due tomorrow
        # would appear twice and be nagged twice in the same tick.
        todos = conn.execute(
            EVENT_SELECT + " where e.item_kind = 'reminder'"
            " and e.acknowledged_at is null",
        ).fetchall()
        rows = list(rows) + list(todos) + [
            occ for occ in project_yearly(yearly, window_start, window_end)
        ]
        already = {
            (r["event_id"], r["kind"])
            for r in conn.execute("select event_id, kind from reminders_sent").fetchall()
        }
        for ev, kind, stored_kind in reminders.pending(rows, already, now, HOUSEHOLD_TZ):
            text = reminders.compose(ev, kind, HOUSEHOLD_TZ, now)
            # A nag carries its Done button; pressing it is the same act as
            # the calendar's checkbox (see bot_tick).
            buttons = ([[{"text": "Done", "callback_data": f"ack:{ev['id']}"}]]
                       if kind == "nag" else None)
            delivered = [c for c in reminders.recipients(ev["owner"])
                         if reminders.send(c, text, buttons)]
            if not delivered:
                # Left unrecorded on purpose, so the next tick retries. If
                # Telegram is down for hours, GRACE eventually gives up.
                continue
            conn.execute(
                "insert into reminders_sent (event_id, kind) values (%s, %s)"
                " on conflict do nothing",
                (ev["id"], stored_kind),
            )
            sent += len(delivered)
    return sent


async def reminder_loop():
    while True:
        try:
            n = await asyncio.to_thread(reminder_tick)
            if n:
                print(f"reminders: sent {n}", flush=True)
        except Exception as exc:  # noqa: BLE001
            # Never let one bad tick end the loop. A calendar that stops
            # reminding silently is worse than one that logs and carries on.
            print(f"reminders: tick failed: {exc!r}", flush=True)
        await asyncio.sleep(reminders.TICK_SECONDS)


def bot_tick() -> int:
    """Collect Done presses and acknowledge their to-dos. Returns acks done.

    The bot's only incoming vocabulary is the callback "ack:<event id>", and
    only from the two chats in CAL_TELEGRAM_CHATS: anything else that reaches
    the bot advances the offset and is otherwise ignored. Pressing Done is
    the same UPDATE the calendar's checkbox runs, one direction only: the
    button acknowledges, and only the calendar UI can un-acknowledge, so a
    mispress in chat is always visible and reversible on the calendar.
    """
    if not reminders.configured():
        return 0
    known = set(reminders.chats().values())
    acked = 0
    with pool.connection() as conn:
        offset = conn.execute(
            "select update_offset from bot_state where id = 1"
        ).fetchone()["update_offset"]
        batch = reminders.updates(offset)
        if not batch:
            return 0
        new_offset = offset
        for u in batch:
            new_offset = max(new_offset, u["update_id"] + 1)
            cb = u.get("callback_query") or {}
            msg = cb.get("message") or {}
            chat = (msg.get("chat") or {}).get("id")
            data = cb.get("data") or ""
            if chat not in known or not data.startswith("ack:"):
                continue
            try:
                event_id = int(data[4:])
            except ValueError:
                continue
            done = conn.execute(
                "update events set acknowledged_at = now()"
                " where id = %s and item_kind = 'reminder'"
                " and acknowledged_at is null",
                (event_id,),
            ).rowcount
            acked += done
            reminders.answer_callback(cb.get("id", ""), "Done ✓")
            reminders.strip_buttons(chat, msg.get("message_id", 0))
        if new_offset != offset:
            conn.execute(
                "update bot_state set update_offset = %s where id = 1",
                (new_offset,),
            )
    return acked


async def bot_loop():
    while True:
        try:
            n = await asyncio.to_thread(bot_tick)
            if n:
                print(f"bot: acknowledged {n}", flush=True)
        except Exception as exc:  # noqa: BLE001
            # Same posture as the reminder loop: log, carry on. A dead poller
            # must never take the reminders down with it.
            print(f"bot: tick failed: {exc!r}", flush=True)
        await asyncio.sleep(reminders.BOT_POLL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open()
    with pool.connection() as conn:
        conn.execute(SCHEMA)
        empty = conn.execute("select count(*) as n from categories").fetchone()["n"] == 0
        if empty:
            # Seeded once, then owned by whoever edits them. Starting from an
            # empty category list means the first event has nothing to pick and
            # the feature looks broken.
            conn.cursor().executemany(
                "insert into categories (name, color, sort_order) values (%s, %s, %s)",
                SEED_CATEGORIES,
            )
    # In-process rather than a systemd timer on the host: it needs the same
    # database, the same timezone handling and the same event query the rest of
    # this module already has, and a second process would duplicate all three.
    # The cost is that reminders stop when the app does, which is acceptable
    # because an app that is down is the larger problem, and the grace window
    # delivers anything that came due during a short outage.
    tasks = []
    if reminders.configured():
        tasks = [asyncio.create_task(reminder_loop()), asyncio.create_task(bot_loop())]
    else:
        print("reminders: no token or no chats configured, loops not started", flush=True)
    yield
    for task in tasks:
        task.cancel()
    pool.close()


class RevalidatingStatic(StaticFiles):
    """Static files that must be revalidated, never served blind from cache.

    FastAPI's StaticFiles sends ETag and Last-Modified but no Cache-Control.
    With no directive at all a browser is free to apply heuristic caching, and
    Chrome does: it kept the first-ever style.css for hours and rendered the
    calendar as an unstyled bullet list on a machine that had loaded the page
    once before. The versioned URLs below fix that on their own; this header is
    the belt to their braces, and costs one conditional request on a LAN.
    """

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app = FastAPI(lifespan=lifespan)
app.mount("/static", RevalidatingStatic(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def front_door(request: Request, call_next):
    """Login only where the trust boundary is (see gate.py): tailnet and LAN
    pass untouched, a public (funnel) visitor needs a session. The stylesheet
    is exempt so the login page can look like the app; the rest of /static is
    NOT, because the wallpapers are family photographs. /health stays open for
    the healthcheck and the homelab monitor, and answers "ok" to anyone."""
    path = request.url.path
    if (
        path in ("/login", "/health")
        or path == "/static/style.css"
        or gate.trusted(request)
        or gate.session_user(request)
    ):
        return await call_next(request)
    q = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/login?next={quote(path + q)}", status_code=303)


def _asset_version() -> str:
    """A short hash of the static assets, appended to their URLs.

    Deploying changes the hash, which changes the URL, which is the only
    cache-busting a browser cannot ignore.
    """
    import hashlib
    import pathlib

    h = hashlib.sha256()
    # rglob, not glob: the pictures live in static/art/ and now in per-person
    # folders below that. A top-level-only hash covered style.css and nothing
    # else, so *replacing* month-10.jpg with a different picture of the same
    # name left the URL and the version unchanged, and the browser kept the old
    # one. The name is part of the hash so a rename counts as a change too.
    for p in sorted(pathlib.Path("static").rglob("*")):
        if p.is_file():
            h.update(str(p).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


ASSET_V = _asset_version()


def shorttime(dt: datetime) -> str:
    """'7p', '6:55p' — the compact 12-hour form for a crowded month cell.

    The meridiem letter is NOT optional, however tight the cell is. A 6:55pm
    flight rendered as "6:55" reads as morning, which is the one mistake a
    calendar must never make.
    """
    suffix = "a" if dt.hour < 12 else "p"
    hour = dt.hour % 12 or 12
    return f"{hour}{suffix}" if dt.minute == 0 else f"{hour}:{dt.minute:02d}{suffix}"


templates.env.filters["shorttime"] = shorttime


# --- time helpers -------------------------------------------------------------


def to_local(dt: datetime) -> datetime:
    return dt.astimezone(HOUSEHOLD_TZ)


def parse_local(s: str) -> datetime:
    """A naive 'YYYY-MM-DDTHH:MM' from a datetime-local input, read as
    household wall-clock time."""
    return datetime.fromisoformat(s).replace(tzinfo=HOUSEHOLD_TZ)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=HOUSEHOLD_TZ)
    return start, start + timedelta(days=1)


def today_local() -> date:
    return datetime.now(HOUSEHOLD_TZ).date()


def parse_day(value: str | None) -> date:
    """A YYYY-MM-DD from the query string, or today.

    A bad one is a 400, never a traceback: these dates arrive in URLs that get
    bookmarked, shared and hand-edited, and `2026-02-29` in a non-leap year is
    an easy thing to type. It used to return 500.
    """
    if not value:
        return today_local()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"not a date: {value}") from None


def decorate(ev: dict) -> dict:
    """Attach the local-time and colour fields every template renders from."""
    ev = dict(ev)
    ev["starts_local"] = to_local(ev["starts_at"])
    ev["ends_local"] = to_local(ev["ends_at"])
    if ev["all_day"]:
        # Stored as [first day 00:00, last day + 1 day 00:00); render the
        # inclusive last day, not the exclusive bound.
        ev["last_day_local"] = (ev["ends_local"] - timedelta(days=1)).date()
    # Category colour wins when there is one; owner colour is the fallback, so
    # an uncategorised event is still readable at a glance.
    ev["color"] = ev.get("category_color") or {
        "Willian": "#4F86E5", "Aline": "#E0679E", "Both": "#4FBF73",
    }.get(ev["owner"], "#8A94A6")
    return ev


# --- queries ------------------------------------------------------------------

EVENT_SELECT = """
select e.*, c.name as category_name, c.color as category_color
from events e left join categories c on c.id = e.category_id
"""


def shift_years(ev: dict, years: int) -> dict:
    """This event's occurrence `years` later, same shape as the original.

    The id is kept, so clicking a projected birthday edits the series, which is
    the only sensible meaning of editing a birthday. February 29th lands on the
    28th in a non-leap year rather than raising, because a birthday that
    crashes the calendar one year in four is not a feature.
    """
    out = dict(ev)
    for key in ("starts_at", "ends_at"):
        dt = ev[key]
        try:
            out[key] = dt.replace(year=dt.year + years)
        except ValueError:
            out[key] = dt.replace(year=dt.year + years, day=28)
    out["occurrence"] = True
    return out


def project_yearly(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Every occurrence of the yearly events that touches [start, end)."""
    out = []
    for ev in rows:
        # The stored date is the first occurrence; nothing repeats backwards.
        for year in range(max(start.year, ev["starts_at"].year), end.year + 1):
            occ = shift_years(ev, year - ev["starts_at"].year)
            if occ["starts_at"] < end and occ["ends_at"] > start:
                out.append(occ)
    return out


def events_between(start: datetime, end: datetime) -> list[dict]:
    with pool.connection() as conn:
        rows = conn.execute(
            EVENT_SELECT + " where e.starts_at < %s and e.ends_at > %s"
            " and not e.repeats_yearly"
            " order by e.all_day desc, e.starts_at, e.id",
            (end, start),
        ).fetchall()
        # Fetched without a date filter, deliberately: a birthday stored in
        # 1990 must surface in 2026, so no starts_at window can find it. The
        # set is small (it is the family's birthdays) and projection is cheap.
        yearly = conn.execute(
            EVENT_SELECT + " where e.repeats_yearly",
        ).fetchall()
    both = [decorate(r) for r in rows] + [decorate(r) for r in project_yearly(yearly, start, end)]
    both.sort(key=lambda e: (not e["all_day"], e["starts_at"], e["id"]))
    return both


def get_event(event_id: int) -> dict:
    with pool.connection() as conn:
        row = conn.execute(EVENT_SELECT + " where e.id = %s", (event_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such event")
    return decorate(row)


def all_categories() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "select * from categories order by sort_order, name"
        ).fetchall()


def overlapping(starts: datetime, ends: datetime, exclude_id: int | None) -> list[dict]:
    """The reason this app exists: everything that intersects [starts, ends).

    Standalone reminders are not booked time, so they neither raise the warning
    nor appear in it: a to-do due Tuesday does not double-book Tuesday.
    """
    with pool.connection() as conn:
        rows = conn.execute(
            EVENT_SELECT + " where e.id is distinct from %s"
            " and e.item_kind = 'event'"
            " and e.starts_at < %s and e.ends_at > %s order by e.starts_at, e.id",
            (exclude_id, ends, starts),
        ).fetchall()
    return [decorate(r) for r in rows]


# --- shared view context ------------------------------------------------------


# How much of the calendar's surface hides the picture. In display order per
# click: default, three steps of more picture, nearly invisible, then one
# extra-solid stop for reading in sunlight, and back around. Values, not free
# input, so the cookie cannot render the calendar unreadable in a way that has
# no obvious way back: one more click always returns to a sane state.
VEIL_STEPS = (72, 52, 32, 14, 4, 88)


def veil_from(request: Request) -> int:
    try:
        v = int(request.cookies.get("cal_veil", ""))
    except ValueError:
        return VEIL_STEPS[0]
    return v if v in VEIL_STEPS else VEIL_STEPS[0]


def base_context(request: Request, view: str, month: int) -> dict:
    who = whois(request)
    path_q = str(request.url.path) + (f"?{request.url.query}" if request.url.query else "")
    return {
        "view": view,
        "who": who,
        "veil": veil_from(request),
        "art": art_for(month, who["key"]),
        "art_month": month,
        "art_accept": ACCEPT_ATTR,
        "art_error": request.query_params.get("art_error"),
        "asset_v": ASSET_V,
        "here": quote(path_q),
        # `here` is percent-encoded because it rides inside other URLs. A form
        # field is NOT one of those places: the value goes through form
        # encoding on its own, and a pre-quoted "/month%3Fy%3D..." would come
        # back as a literal path and 404 on redirect. Forms take this one.
        "here_plain": path_q,
    }


def lay_out_day(events: list[dict], day: date) -> list[dict]:
    """Position timed events in a day column: top/height as percentages of 24h,
    and side-by-side lanes for the ones that overlap.

    Without lanes, two events at the same hour render exactly on top of each
    other and the second one is invisible — which would hide precisely the
    double-booking this calendar exists to surface.
    """
    ds, de = day_bounds(day)
    placed = []
    for e in events:
        start = max(e["starts_at"], ds)
        end = min(e["ends_at"], de)
        minutes = (start - ds).total_seconds() / 60
        length = max((end - start).total_seconds() / 60, 30)  # 30min floor to stay clickable
        placed.append({**e, "_start": start, "_end": end,
                       "top_pct": minutes / 14.4, "height_pct": min(length / 14.4, 100 - minutes / 14.4)})

    placed.sort(key=lambda x: (x["_start"], x["_end"]))
    # Cluster by overlap, then assign lanes within each cluster so widths are
    # computed against the events actually competing for the same space.
    cluster: list[dict] = []
    cluster_end = None
    for e in placed:
        if cluster and cluster_end is not None and e["_start"] >= cluster_end:
            _assign_lanes(cluster)
            cluster, cluster_end = [], None
        cluster.append(e)
        cluster_end = max(cluster_end or e["_end"], e["_end"])
    if cluster:
        _assign_lanes(cluster)
    return placed


def _assign_lanes(cluster: list[dict]) -> None:
    lanes: list[datetime] = []
    for e in cluster:
        for i, busy_until in enumerate(lanes):
            if e["_start"] >= busy_until:
                e["lane"], lanes[i] = i, e["_end"]
                break
        else:
            e["lane"] = len(lanes)
            lanes.append(e["_end"])
    n = len(lanes)
    for e in cluster:
        e["lane_count"] = n
        e["left_pct"] = 100 * e["lane"] / n
        e["width_pct"] = 100 / n


# --- views --------------------------------------------------------------------


@app.get("/health")
def health() -> JSONResponse:
    with pool.connection() as conn:
        conn.execute("select 1")
    return JSONResponse({"status": "ok"})


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/month", status_code=307)


@app.get("/month", response_class=HTMLResponse)
def month_view(request: Request, y: int | None = None, m: int | None = None):
    today = today_local()
    y, m = y or today.year, m or today.month
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise HTTPException(status_code=400, detail="out of range")

    # Sunday-first weeks; the grid includes the padding days that fill the
    # month out to whole weeks, so events are fetched for the padded range.
    weeks = Calendar(firstweekday=6).monthdatescalendar(y, m)
    grid_start, _ = day_bounds(weeks[0][0])
    _, grid_end = day_bounds(weeks[-1][-1])
    events = events_between(grid_start, grid_end)

    days = {}
    for week in weeks:
        for d in week:
            ds, de = day_bounds(d)
            days[d] = [e for e in events if e["starts_at"] < de and e["ends_at"] > ds]

    prev = (date(y, m, 1) - timedelta(days=1)).replace(day=1)
    nxt = (date(y, m, 28) + timedelta(days=7)).replace(day=1)

    ctx = base_context(request, "month", m)
    ctx.update(
        weeks=weeks, days=days, year=y, month=m,
        month_name=date(y, m, 1).strftime("%B"), today=today,
        prev=prev, next=nxt,
        holidays=holidays_between(weeks[0][0], weeks[-1][-1]),
        releases=news.releases(y, m, today_local()),
        categories=all_categories(),
    )
    return templates.TemplateResponse(request, "month.html", ctx)


@app.get("/week", response_class=HTMLResponse)
def week_view(request: Request, d: str | None = None):
    focus = parse_day(d)
    start = focus - timedelta(days=(focus.weekday() + 1) % 7)  # back to Sunday
    week = [start + timedelta(days=i) for i in range(7)]

    ws, _ = day_bounds(week[0])
    _, we = day_bounds(week[-1])
    events = events_between(ws, we)

    all_day, timed = {}, {}
    for day in week:
        ds, de = day_bounds(day)
        here = [e for e in events if e["starts_at"] < de and e["ends_at"] > ds]
        all_day[day] = [e for e in here if e["all_day"]]
        timed[day] = lay_out_day([e for e in here if not e["all_day"]], day)

    # Open the grid on the week's earliest event rather than on midnight, and
    # fall back to 07:00 for an empty week. Computed here because the server
    # knows the times; the browser would have to measure them back out of the
    # DOM.
    starts = [e["starts_local"] for day in week for e in timed[day]]
    first_minute = min(
        (s.hour * 60 + s.minute for s in starts), default=7 * 60
    )
    scroll_minute = max(0, first_minute - 45)

    # The picture follows the month the week mostly sits in.
    ctx = base_context(request, "week", week[3].month)
    ctx.update(
        week=week, all_day=all_day, timed=timed, today=today_local(),
        scroll_minute=scroll_minute,
        prev=(start - timedelta(days=7)).isoformat(),
        next=(start + timedelta(days=7)).isoformat(),
        hours=list(range(24)),
        holidays=holidays_between(week[0], week[-1]),
        releases=news.releases(focus.year, focus.month, today_local()),
        categories=all_categories(),
        label=(f"{week[0].strftime('%b %-d')} – {week[-1].strftime('%b %-d, %Y')}"),
    )
    return templates.TemplateResponse(request, "week.html", ctx)


@app.get("/upcoming", response_class=HTMLResponse)
def upcoming_view(request: Request):
    now = datetime.now(HOUSEHOLD_TZ)
    horizon = now + timedelta(days=60)
    events = events_between(now, horizon)

    by_day: dict[date, list[dict]] = {}
    for e in events:
        # An in-progress multi-day event files under today, not its start day.
        key = max(e["starts_local"].date(), now.date())
        by_day.setdefault(key, []).append(e)

    # An overdue to-do has already left the [now, horizon) window that feeds
    # this view, which is exactly when its OK button matters most: this is the
    # only view that is not date-navigational, so without this section the
    # button would only exist back on the day the item was due. Acknowledged
    # ones stay gone; done is done.
    with pool.connection() as conn:
        overdue = [decorate(r) for r in conn.execute(
            EVENT_SELECT + " where e.item_kind = 'reminder'"
            " and e.acknowledged_at is null and e.ends_at <= %s"
            " order by e.starts_at, e.id",
            (now,),
        ).fetchall()]

    ctx = base_context(request, "upcoming", now.month)
    ctx.update(
        by_day=sorted(by_day.items()), overdue=overdue, today=now.date(),
        holidays=holidays_between(now.date(), horizon.date()),
        releases=news.releases(now.year, now.month, today_local()),
        categories=all_categories(),
    )
    return templates.TemplateResponse(request, "upcoming.html", ctx)


# --- create / edit ------------------------------------------------------------


def form_context(request: Request, ev: dict | None, day: date, back: str,
                 hour: int | None = None, until: int | None = None) -> dict:
    # hour/until come from the week grid: clicking one slot gives an hour,
    # dragging across several gives a range. Without either, the form guesses
    # the next round hour, which is the sane default when the click carried no
    # time with it.
    if hour is None:
        start_hour = (datetime.now(HOUSEHOLD_TZ) + timedelta(hours=1)).hour
    else:
        start_hour = max(0, min(23, hour))
    default_start = datetime.combine(day, time(start_hour, 0), tzinfo=HOUSEHOLD_TZ)
    # `until` is the exclusive end hour, so dragging 6 to 8 means 6:00-9:00.
    # 24 has to survive as an end, which is why it is not clamped to 23.
    end_hour = max(start_hour + 1, min(24, until)) if until is not None else start_hour + 1
    default_end = datetime.combine(day, time.min, tzinfo=HOUSEHOLD_TZ) + timedelta(hours=end_hour)
    ctx = base_context(request, "form", day.month)
    ctx.update(
        request=request, ev=ev, owners=OWNERS, back=back,
        categories=all_categories(), palette=PALETTE, stickers=STICKERS,
        default_start=default_start, default_end=default_end,
        conflicts=None, error=None,
    )
    return ctx


@app.get("/events/new", response_class=HTMLResponse)
def new_event_form(request: Request, day: str | None = None, back: str = "/month",
                   hour: int | None = None, until: int | None = None):
    return templates.TemplateResponse(
        request, "event_form.html",
        form_context(request, None, parse_day(day), back, hour, until),
    )


@app.get("/events/{event_id}/edit", response_class=HTMLResponse)
def edit_event_form(request: Request, event_id: int, back: str = "/month"):
    ev = get_event(event_id)
    return templates.TemplateResponse(
        request, "event_form.html",
        form_context(request, ev, ev["starts_local"].date(), back),
    )


@app.post("/events/save", response_class=HTMLResponse)
def save_event(
    request: Request,
    event_id: str = Form(""),
    title: str = Form(""),
    owner: str = Form(...),
    category_id: str = Form(""),
    sticker: str = Form(""),
    all_day: str = Form(""),
    reminder: str = Form(""),
    repeats_yearly: str = Form(""),
    starts: str = Form(""),
    ends: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
    back: str = Form("/month"),
    confirmed: str = Form(""),
):
    eid = int(event_id) if event_id else None
    cid = int(category_id) if category_id else None
    is_reminder = reminder == "on"
    # A reminder is a single all-day row by construction, never yearly. Forced
    # here rather than trusted from the form: the form hides those controls
    # when the reminder box is ticked, and a hidden checkbox still posts.
    # Yearly is not a UI nicety but a correctness rule: a projected occurrence
    # copies the row wholesale, acknowledged_at included, so a yearly to-do
    # acknowledged once would silently never nag again in any later year.
    is_all_day = True if is_reminder else all_day == "on"
    is_yearly = False if is_reminder else repeats_yearly == "on"

    def rerender(error: str | None, conflicts: list[dict] | None):
        """Re-show the form with what was typed, not what is stored."""
        ev = {
            "id": eid, "title": title, "owner": owner, "all_day": is_all_day,
            "repeats_yearly": is_yearly,
            "item_kind": "reminder" if is_reminder else "event",
            "location": location, "notes": notes, "category_id": cid,
            "sticker": sticker,
            "form_starts": starts, "form_ends": ends,
            "form_start_date": start_date, "form_end_date": end_date,
        }
        ctx = form_context(request, ev, today_local(), back)
        ctx["conflicts"], ctx["error"] = conflicts, error
        return templates.TemplateResponse(request, "event_form.html", ctx)

    if not title.strip():
        return rerender("A title is required.", None)
    if owner not in OWNERS:
        return rerender("Pick who this event belongs to.", None)

    try:
        if is_all_day:
            first = date.fromisoformat(start_date)
            # A reminder has one date, the due date; the last-day field is not
            # even shown for it, so whatever it still holds is ignored.
            last = first if is_reminder else date.fromisoformat(end_date or start_date)
            if last < first:
                return rerender("The last day is before the first day.", None)
            starts_at, _ = day_bounds(first)
            _, ends_at = day_bounds(last)
        else:
            starts_at, ends_at = parse_local(starts), parse_local(ends)
            if ends_at <= starts_at:
                return rerender("The end must be after the start.", None)
    except ValueError:
        return rerender("Fill in the dates and times.", None)

    # The whole point: warn about a double booking, but never block the save.
    # Some overlaps are deliberate (two things during one trip), so the warning
    # asks rather than refuses. Reminders skip it from this side too: saving a
    # to-do on a busy day is not a double booking.
    if confirmed != "1" and not is_reminder:
        conflicts = overlapping(starts_at, ends_at, eid)
        if conflicts:
            return rerender(None, conflicts)

    values = (title.strip(), starts_at, ends_at, is_all_day, owner,
              location.strip(), notes.strip(), cid, sticker.strip()[:8], is_yearly,
              "reminder" if is_reminder else "event")
    with pool.connection() as conn:
        if eid is None:
            conn.execute(
                "insert into events (title, starts_at, ends_at, all_day, owner,"
                " location, notes, category_id, sticker, repeats_yearly, item_kind)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", values,
            )
        else:
            # acknowledged_at is deliberately not touched here: fixing a typo
            # on a finished to-do must not reopen it. Only the OK button moves
            # that column, in either direction.
            conn.execute(
                "update events set title=%s, starts_at=%s, ends_at=%s, all_day=%s,"
                " owner=%s, location=%s, notes=%s, category_id=%s, sticker=%s,"
                " repeats_yearly=%s, item_kind=%s, updated_at=now() where id=%s",
                values + (eid,),
            )
            # Re-arm the reminders. An edit is usually a reschedule or a change
            # of owner, and both make the reminder that was already sent wrong:
            # without this, moving a dinner from Tuesday to Friday means nobody
            # is ever told about Friday.
            conn.execute("delete from reminders_sent where event_id = %s", (eid,))

    # Land on the month the event is in, which is not necessarily the one the
    # form was opened from.
    local = to_local(starts_at)
    return RedirectResponse(f"/month?y={local.year}&m={local.month}", status_code=303)


@app.post("/events/{event_id}/delete")
def delete_event(event_id: int, back: str = Form("/month")):
    with pool.connection() as conn:
        conn.execute("delete from events where id = %s", (event_id,))
    return RedirectResponse(back, status_code=303)


@app.post("/events/{event_id}/ack")
def toggle_ack(event_id: int, back: str = Form("/month")):
    """The OK on a to-do, and its undo: the same button pressed again.

    A toggle rather than a one-way ack because the misclick is symmetric: the
    box sits next to the title in every view, and "oops, that silenced the
    matricula nag" needs a way back that is not the edit form. Guarded to
    reminders so a stray POST cannot stamp acknowledged_at onto a real event,
    where nothing would ever show or clear it.
    """
    with pool.connection() as conn:
        conn.execute(
            "update events set acknowledged_at ="
            " case when acknowledged_at is null then now() else null end"
            " where id = %s and item_kind = 'reminder'",
            (event_id,),
        )
    return RedirectResponse(back, status_code=303)


# --- the front door (funnel visitors only; see gate.py) ------------------------


def _safe_next(n: str) -> str:
    """Only same-app paths: a full URL or scheme-relative //host in `next`
    would turn the login into an open redirect."""
    return n if n.startswith("/") and not n.startswith("//") else "/month"


def _login_ctx(request: Request, nxt: str, error: str | None) -> dict:
    return {
        "request": request,
        "next": _safe_next(nxt),
        "error": error,
        "configured": gate.configured(),
        "people": PEOPLE,
        "asset_v": ASSET_V,
    }


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/month"):
    # A tailnet device or an existing session has no business at the door.
    if gate.trusted(request) or gate.session_user(request):
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "login.html", _login_ctx(request, next, None))


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, who: str = Form(""), password: str = Form(""),
                 next: str = Form("/month")):
    who = who.strip().lower()
    if not gate.configured():
        return templates.TemplateResponse(
            request, "login.html", _login_ctx(request, next, None))
    if not gate.check_password(who, password):
        # A flat second per wrong guess. Not a fortress, but brute force from
        # the funnel should at least have to wait in line.
        systime.sleep(1)
        return templates.TemplateResponse(
            request, "login.html", _login_ctx(request, next, "Wrong name or password."))
    resp = RedirectResponse(_safe_next(next), status_code=303)
    resp.set_cookie(gate.COOKIE, gate.mint(who), max_age=gate.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=True)
    # Logging in also says whose pictures these are, same contract as /who.
    if who in PEOPLE:
        resp.set_cookie("cal_who", who, max_age=31536000, samesite="lax", httponly=True)
    return resp


# --- categories ---------------------------------------------------------------


@app.get("/categories", response_class=HTMLResponse)
def categories_view(request: Request, back: str = "/month"):
    ctx = base_context(request, "categories", today_local().month)
    with pool.connection() as conn:
        counts = {
            r["category_id"]: r["n"]
            for r in conn.execute(
                "select category_id, count(*) as n from events"
                " where category_id is not null group by category_id"
            ).fetchall()
        }
    ctx.update(categories=all_categories(), palette=PALETTE, counts=counts, back=back)
    return templates.TemplateResponse(request, "categories.html", ctx)


@app.post("/categories/save")
def save_category(name: str = Form(""), color: str = Form("#4F86E5"),
                  category_id: str = Form("")):
    name = name.strip()[:40]
    if not name:
        return RedirectResponse("/categories", status_code=303)
    with pool.connection() as conn:
        if category_id:
            conn.execute(
                "update categories set name=%s, color=%s where id=%s",
                (name, color, int(category_id)),
            )
        else:
            # A duplicate name is a re-submit or a typo, not an error worth a
            # page: update the colour of the one that already exists.
            conn.execute(
                "insert into categories (name, color) values (%s, %s)"
                " on conflict (name) do update set color = excluded.color",
                (name, color),
            )
    return RedirectResponse("/categories", status_code=303)


@app.post("/categories/{category_id}/delete")
def delete_category(category_id: int):
    # Events keep their place and fall back to the owner colour, because
    # `on delete set null` is on the column. Deleting a category must never
    # delete anything from the calendar itself.
    with pool.connection() as conn:
        conn.execute("delete from categories where id = %s", (category_id,))
    return RedirectResponse("/categories", status_code=303)


# --- who is looking -----------------------------------------------------------


@app.get("/who", response_class=HTMLResponse)
def who_view(request: Request, back: str = "/month"):
    """Shows what the app thinks it is looking at, and lets that be overridden.

    This doubles as the diagnostic for the whole arrangement: if someone's
    pictures are wrong, this page reports the tailnet address the request
    arrived with, which is the value that has to appear in CAL_DEVICES.
    """
    ctx = base_context(request, "who", today_local().month)
    months = [
        (m, date(2000, m, 1).strftime("%B"), art_for(m, ctx["who"]["key"]))
        for m in range(1, 13)
    ]
    ctx.update(people=PEOPLE, months=months, back=back)
    return templates.TemplateResponse(request, "who.html", ctx)


@app.post("/veil")
def cycle_veil(request: Request, back: str = Form("/month")):
    """One button, one direction: each press shows more of the picture, through
    nearly invisible, then a solid stop, then back to the default. Per device
    via cookie, same reasoning as the pictures: what reads well on a monitor is
    unreadable on a phone in the sun, and the two should not have to agree."""
    current = veil_from(request)
    nxt = VEIL_STEPS[(VEIL_STEPS.index(current) + 1) % len(VEIL_STEPS)]
    resp = RedirectResponse(back, status_code=303)
    resp.set_cookie("cal_veil", str(nxt), max_age=31536000, samesite="lax", httponly=True)
    return resp


@app.post("/who")
def set_who(who: str = Form(""), back: str = Form("/month")):
    """A cookie, not a session: it decides which pictures to draw and nothing
    else, so there is nothing in it worth protecting."""
    who = who.strip().lower()
    resp = RedirectResponse(back, status_code=303)
    if who == "auto":
        resp.delete_cookie("cal_who")
    elif who in PEOPLE or who == "shared":
        # A year, because the alternative is being asked again on a phone that
        # has done nothing wrong.
        resp.set_cookie("cal_who", who, max_age=31536000, samesite="lax", httponly=True)
    return resp


@app.post("/art/upload")
async def upload_art(request: Request, file: UploadFile = File(...),
                     month: int = Form(...), back: str = Form("/month"),
                     scope: str = Form("mine")):
    """Set the background for one month from the browser.

    It lands in the uploader's own folder by default, so changing your October
    does not change hers. `scope=shared` writes the level everyone sees, which
    is the right choice for a picture of the two of them.
    """
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="month must be 1-12")
    who = whois(request)
    person = None if scope == "shared" else who["key"]
    try:
        save_month_art(month, person, await file.read(MAX_UPLOAD_BYTES + 1))
    except ArtError as e:
        # The message is written for the person, so it is worth showing rather
        # than swallowing into a 400 page.
        return RedirectResponse(f"{back}{'&' if '?' in back else '?'}art_error={quote(str(e))}",
                                status_code=303)
    return RedirectResponse(back, status_code=303)


@app.post("/art/remove")
def remove_art(request: Request, month: int = Form(...), back: str = Form("/month"),
               scope: str = Form("mine")):
    who = whois(request)
    remove_month_art(month, None if scope == "shared" else who["key"])
    return RedirectResponse(back, status_code=303)
