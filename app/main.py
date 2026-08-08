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
#   Tailscale account, so no header can tell one of us from the other. The
#   event says whose it is; the infrastructure cannot.

import os
from calendar import Calendar
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

import news
from holidays import holidays_between
from themes import THEMES, theme_choices, theme_for

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
    yield
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


def _asset_version() -> str:
    """A short hash of the static assets, appended to their URLs.

    Deploying changes the hash, which changes the URL, which is the only
    cache-busting a browser cannot ignore.
    """
    import hashlib
    import pathlib

    h = hashlib.sha256()
    for p in sorted(pathlib.Path("static").glob("*")):
        if p.is_file():
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


def events_between(start: datetime, end: datetime) -> list[dict]:
    with pool.connection() as conn:
        rows = conn.execute(
            EVENT_SELECT + " where e.starts_at < %s and e.ends_at > %s"
            " order by e.all_day desc, e.starts_at, e.id",
            (end, start),
        ).fetchall()
    return [decorate(r) for r in rows]


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
    """The reason this app exists: everything that intersects [starts, ends)."""
    with pool.connection() as conn:
        rows = conn.execute(
            EVENT_SELECT + " where e.id is distinct from %s"
            " and e.starts_at < %s and e.ends_at > %s order by e.starts_at, e.id",
            (exclude_id, ends, starts),
        ).fetchall()
    return [decorate(r) for r in rows]


# --- shared view context ------------------------------------------------------


def base_context(request: Request, view: str, theme_override: str | None,
                 span: tuple[date, date]) -> dict:
    theme = theme_for(span[0], span[1], theme_override)
    return {
        "view": view,
        "theme": theme,
        "asset_v": ASSET_V,
        "theme_choices": theme_choices(),
        "theme_override": theme_override or "",
        "here": quote(str(request.url.path) + (f"?{request.url.query}" if request.url.query else "")),
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
def month_view(request: Request, y: int | None = None, m: int | None = None,
               theme: str | None = None):
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

    # The theme follows the MONTH, not the padded grid. The grid runs into the
    # neighbouring months to fill whole weeks, and using its span made November
    # look like Christmas because the trailing days reach December.
    last_day = (date(y, m, 28) + timedelta(days=7)).replace(day=1) - timedelta(days=1)
    ctx = base_context(request, "month", theme, (date(y, m, 1), last_day))
    ctx.update(
        weeks=weeks, days=days, year=y, month=m,
        month_name=date(y, m, 1).strftime("%B"), today=today,
        prev=prev, next=nxt,
        holidays=holidays_between(weeks[0][0], weeks[-1][-1]),
        releases=news.releases(y, m),
        categories=all_categories(),
    )
    return templates.TemplateResponse(request, "month.html", ctx)


@app.get("/week", response_class=HTMLResponse)
def week_view(request: Request, d: str | None = None, theme: str | None = None):
    focus = date.fromisoformat(d) if d else today_local()
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

    ctx = base_context(request, "week", theme, (week[0], week[-1]))
    ctx.update(
        week=week, all_day=all_day, timed=timed, today=today_local(),
        scroll_minute=scroll_minute,
        prev=(start - timedelta(days=7)).isoformat(),
        next=(start + timedelta(days=7)).isoformat(),
        hours=list(range(24)),
        holidays=holidays_between(week[0], week[-1]),
        releases=news.releases(focus.year, focus.month),
        categories=all_categories(),
        label=(f"{week[0].strftime('%b %-d')} – {week[-1].strftime('%b %-d, %Y')}"),
    )
    return templates.TemplateResponse(request, "week.html", ctx)


@app.get("/upcoming", response_class=HTMLResponse)
def upcoming_view(request: Request, theme: str | None = None):
    now = datetime.now(HOUSEHOLD_TZ)
    horizon = now + timedelta(days=60)
    events = events_between(now, horizon)

    by_day: dict[date, list[dict]] = {}
    for e in events:
        # An in-progress multi-day event files under today, not its start day.
        key = max(e["starts_local"].date(), now.date())
        by_day.setdefault(key, []).append(e)

    ctx = base_context(request, "upcoming", theme, (now.date(), horizon.date()))
    ctx.update(
        by_day=sorted(by_day.items()), today=now.date(),
        holidays=holidays_between(now.date(), horizon.date()),
        releases=news.releases(now.year, now.month),
        categories=all_categories(),
    )
    return templates.TemplateResponse(request, "upcoming.html", ctx)


# --- create / edit ------------------------------------------------------------


def form_context(request: Request, ev: dict | None, day: date, back: str,
                 hour: int | None = None) -> dict:
    # An explicit hour comes from clicking a slot in the week grid; without one
    # the form guesses the next round hour, which is the sane default when the
    # click carried no time with it.
    if hour is None:
        start_hour = (datetime.now(HOUSEHOLD_TZ) + timedelta(hours=1)).hour
    else:
        start_hour = max(0, min(23, hour))
    default_start = datetime.combine(day, time(start_hour, 0), tzinfo=HOUSEHOLD_TZ)
    ctx = base_context(request, "form", None, (day, day))
    ctx.update(
        request=request, ev=ev, owners=OWNERS, back=back,
        categories=all_categories(), palette=PALETTE, stickers=STICKERS,
        default_start=default_start, default_end=default_start + timedelta(hours=1),
        conflicts=None, error=None,
    )
    return ctx


@app.get("/events/new", response_class=HTMLResponse)
def new_event_form(request: Request, day: str | None = None, back: str = "/month",
                   hour: int | None = None):
    d = date.fromisoformat(day) if day else today_local()
    return templates.TemplateResponse(
        request, "event_form.html", form_context(request, None, d, back, hour)
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
    is_all_day = all_day == "on"

    def rerender(error: str | None, conflicts: list[dict] | None):
        """Re-show the form with what was typed, not what is stored."""
        ev = {
            "id": eid, "title": title, "owner": owner, "all_day": is_all_day,
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
            last = date.fromisoformat(end_date or start_date)
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
    # asks rather than refuses.
    if confirmed != "1":
        conflicts = overlapping(starts_at, ends_at, eid)
        if conflicts:
            return rerender(None, conflicts)

    values = (title.strip(), starts_at, ends_at, is_all_day, owner,
              location.strip(), notes.strip(), cid, sticker.strip()[:8])
    with pool.connection() as conn:
        if eid is None:
            conn.execute(
                "insert into events (title, starts_at, ends_at, all_day, owner,"
                " location, notes, category_id, sticker)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s)", values,
            )
        else:
            conn.execute(
                "update events set title=%s, starts_at=%s, ends_at=%s, all_day=%s,"
                " owner=%s, location=%s, notes=%s, category_id=%s, sticker=%s,"
                " updated_at=now() where id=%s", values + (eid,),
            )

    # Land on the month the event is in, which is not necessarily the one the
    # form was opened from.
    local = to_local(starts_at)
    return RedirectResponse(f"/month?y={local.year}&m={local.month}", status_code=303)


@app.post("/events/{event_id}/delete")
def delete_event(event_id: int, back: str = Form("/month")):
    with pool.connection() as conn:
        conn.execute("delete from events where id = %s", (event_id,))
    return RedirectResponse(back, status_code=303)


# --- categories ---------------------------------------------------------------


@app.get("/categories", response_class=HTMLResponse)
def categories_view(request: Request, back: str = "/month"):
    ctx = base_context(request, "categories", None, (today_local(), today_local()))
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
