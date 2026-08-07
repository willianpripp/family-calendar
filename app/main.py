# The family calendar. Small on purpose: one file, no ORM, no migrations
# framework. The schema is applied idempotently at startup, which is the right
# size of machinery for one table and two users.
#
# The two design points that matter more than they look (see homelab STATUS):
#
#   Timezone. The host stores timestamptz (UTC); every parse and every render
#   goes through HOUSEHOLD_TZ explicitly. Form input arrives as naive local
#   wall-clock time and is localized here, never trusted as UTC. A calendar
#   silently four hours out is worse than none.
#
#   Ownership is an explicit field. Every family device signs in as the same
#   Tailscale account, so no header can tell Willian from Aline. The event says
#   whose it is; the infrastructure cannot.

import os
from calendar import Calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

HOUSEHOLD_TZ = ZoneInfo(os.environ.get("CAL_TZ", "America/New_York"))
OWNERS = ("Willian", "Aline", "Both")

SCHEMA = """
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
"""

pool = ConnectionPool(
    os.environ["DATABASE_URL"], min_size=1, max_size=4, kwargs={"row_factory": dict_row}
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def apply_schema() -> None:
    with pool.connection() as conn:
        conn.execute(SCHEMA)


# --- time helpers -------------------------------------------------------------


def to_local(dt: datetime) -> datetime:
    return dt.astimezone(HOUSEHOLD_TZ)


def parse_local(s: str) -> datetime:
    """A naive 'YYYY-MM-DDTHH:MM' from a datetime-local input, as household
    wall-clock time."""
    return datetime.fromisoformat(s).replace(tzinfo=HOUSEHOLD_TZ)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=HOUSEHOLD_TZ)
    return start, start + timedelta(days=1)


def decorate(ev: dict) -> dict:
    """Attach the local-time fields every template renders from."""
    ev = dict(ev)
    ev["starts_local"] = to_local(ev["starts_at"])
    ev["ends_local"] = to_local(ev["ends_at"])
    if ev["all_day"]:
        # Stored as [day 00:00, last day + 1 day 00:00); render the inclusive
        # last day, not the exclusive bound.
        ev["last_day_local"] = (ev["ends_local"] - timedelta(days=1)).date()
    return ev


# --- queries ------------------------------------------------------------------


def events_between(start: datetime, end: datetime) -> list[dict]:
    with pool.connection() as conn:
        rows = conn.execute(
            "select * from events where starts_at < %s and ends_at > %s order by starts_at, id",
            (end, start),
        ).fetchall()
    return [decorate(r) for r in rows]


def get_event(event_id: int) -> dict:
    with pool.connection() as conn:
        row = conn.execute("select * from events where id = %s", (event_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such event")
    return decorate(row)


def overlapping(starts: datetime, ends: datetime, exclude_id: int | None) -> list[dict]:
    """The reason this app exists: everything that intersects [starts, ends)."""
    with pool.connection() as conn:
        rows = conn.execute(
            "select * from events where id is distinct from %s"
            " and starts_at < %s and ends_at > %s order by starts_at, id",
            (exclude_id, ends, starts),
        ).fetchall()
    return [decorate(r) for r in rows]


# --- views --------------------------------------------------------------------


@app.get("/health")
def health() -> JSONResponse:
    with pool.connection() as conn:
        conn.execute("select 1")
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    return RedirectResponse("/month", status_code=307)


@app.get("/month", response_class=HTMLResponse)
def month_view(request: Request, y: int | None = None, m: int | None = None):
    today = datetime.now(HOUSEHOLD_TZ).date()
    y, m = y or today.year, m or today.month
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise HTTPException(status_code=400, detail="out of range")

    # Sunday-first weeks; the grid includes the leading/trailing days that pad
    # the month to whole weeks, so events are fetched for the padded range.
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
    return templates.TemplateResponse(
        request,
        "month.html",
        {
            "weeks": weeks,
            "days": days,
            "year": y,
            "month": m,
            "month_name": date(y, m, 1).strftime("%B"),
            "today": today,
            "prev": prev,
            "next": nxt,
            "view": "month",
        },
    )


@app.get("/upcoming", response_class=HTMLResponse)
def upcoming_view(request: Request):
    now = datetime.now(HOUSEHOLD_TZ)
    horizon = now + timedelta(days=60)
    events = [e for e in events_between(now, horizon)]

    by_day: dict[date, list[dict]] = {}
    for e in events:
        # An in-progress multi-day event files under today, not its start day.
        key = max(e["starts_local"].date(), now.date())
        by_day.setdefault(key, []).append(e)

    return templates.TemplateResponse(
        request,
        "upcoming.html",
        {"by_day": sorted(by_day.items()), "today": now.date(), "view": "upcoming"},
    )


# --- create / edit ------------------------------------------------------------


def form_context(request: Request, ev: dict | None, day: date, back: str) -> dict:
    now_local = datetime.now(HOUSEHOLD_TZ)
    default_start = datetime.combine(day, time(now_local.hour, 0), tzinfo=HOUSEHOLD_TZ) + timedelta(hours=1)
    return {
        "request": request,
        "ev": ev,
        "owners": OWNERS,
        "back": back,
        "default_start": default_start,
        "default_end": default_start + timedelta(hours=1),
        "conflicts": None,
        "error": None,
    }


@app.get("/events/new", response_class=HTMLResponse)
def new_event_form(request: Request, day: str | None = None, back: str = "/month"):
    d = date.fromisoformat(day) if day else datetime.now(HOUSEHOLD_TZ).date()
    ctx = form_context(request, None, d, back)
    return templates.TemplateResponse(request, "event_form.html", ctx)


@app.get("/events/{event_id}/edit", response_class=HTMLResponse)
def edit_event_form(request: Request, event_id: int, back: str = "/month"):
    ev = get_event(event_id)
    ctx = form_context(request, ev, ev["starts_local"].date(), back)
    return templates.TemplateResponse(request, "event_form.html", ctx)


@app.post("/events/save", response_class=HTMLResponse)
def save_event(
    request: Request,
    event_id: str = Form(""),
    title: str = Form(""),
    owner: str = Form(...),
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
    is_all_day = all_day == "on"

    def rerender(error: str | None, conflicts: list[dict] | None):
        """Re-show the form with what was typed, not what is stored."""
        ev = {
            "id": eid,
            "title": title,
            "owner": owner,
            "all_day": is_all_day,
            "location": location,
            "notes": notes,
            "form_starts": starts,
            "form_ends": ends,
            "form_start_date": start_date,
            "form_end_date": end_date,
        }
        ctx = form_context(request, ev, datetime.now(HOUSEHOLD_TZ).date(), back)
        ctx["conflicts"], ctx["error"] = conflicts, error
        return templates.TemplateResponse(request, "event_form.html", ctx)

    if not title.strip():
        return rerender("A title is required.", None)
    if owner not in OWNERS:
        return rerender("Pick who this event belongs to.", None)

    try:
        if is_all_day:
            first, last = date.fromisoformat(start_date), date.fromisoformat(end_date or start_date)
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
    # Some overlaps are deliberate (two events during one trip), so the warning
    # asks rather than refuses.
    if confirmed != "1":
        conflicts = overlapping(starts_at, ends_at, eid)
        if conflicts:
            return rerender(None, conflicts)

    with pool.connection() as conn:
        if eid is None:
            conn.execute(
                "insert into events (title, starts_at, ends_at, all_day, owner, location, notes)"
                " values (%s, %s, %s, %s, %s, %s, %s)",
                (title.strip(), starts_at, ends_at, is_all_day, owner, location.strip(), notes.strip()),
            )
        else:
            conn.execute(
                "update events set title=%s, starts_at=%s, ends_at=%s, all_day=%s,"
                " owner=%s, location=%s, notes=%s, updated_at=now() where id=%s",
                (title.strip(), starts_at, ends_at, is_all_day, owner, location.strip(), notes.strip(), eid),
            )

    # Land on the month the event is in, which is not necessarily the current one.
    local = to_local(starts_at)
    return RedirectResponse(f"/month?y={local.year}&m={local.month}", status_code=303)


@app.post("/events/{event_id}/delete")
def delete_event(event_id: int, back: str = Form("/month")):
    with pool.connection() as conn:
        conn.execute("delete from events where id = %s", (event_id,))
    return RedirectResponse(back, status_code=303)
