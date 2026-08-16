# "What's on" for the rail beside the calendar. It exists because of an AMC
# A-List subscription and a weekly cinema habit, so the question it answers is
# "what could we go see", not "what exists".
#
# That distinction decides which TMDB endpoint gets used, and it is not
# cosmetic. Asking /discover for a month that has not happened yet returns
# titles sorted by a popularity score they have not earned: for August 2026 it
# offered a Korean comedy and an Indian war film ahead of anything playing at
# an ordinary US multiplex. TMDB's curated /movie/now_playing for the US region
# returns Spider-Man and The Odyssey, which is the honest answer to "what is at
# the cinema this week".
#
# So: the current month shows what is IN theatres now, plus what still opens
# before the month is out. Any other month shows that month's wide releases,
# which is all that can be known about it.
#
# Needs CAL_TMDB_KEY. WITHOUT IT THE RAIL SAYS SO AND NOTHING ELSE CHANGES —
# every failure path returns empty sections and a reason rather than raising,
# because a film database must never be able to take the calendar down.

import calendar as _calendar
import os
import threading
import time
from calendar import monthrange
from datetime import date

import httpx

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w92"
TTL_SECONDS = 6 * 60 * 60

_cache: dict[tuple[int, int, str], tuple[float, dict]] = {}
_lock = threading.Lock()


def configured() -> bool:
    return bool(os.environ.get("CAL_TMDB_KEY", "").strip())


def _auth() -> tuple[dict, dict]:
    """(query params, headers) for whichever kind of key is set.

    TMDB's settings page offers TWO credentials and it is easy to copy the
    wrong one: a short v3 "API Key" for the query string, and a long v4 "API
    Read Access Token" (a JWT, starting `eyJ`) for an Authorization header.
    Both are accepted, because "I pasted the one that was on screen" is not a
    mistake worth debugging twice.
    """
    key = os.environ.get("CAL_TMDB_KEY", "").strip()
    if key.startswith("eyJ"):
        return {}, {"Authorization": f"Bearer {key}", "accept": "application/json"}
    return {"api_key": key}, {}


def _get(path: str, params: dict | None = None) -> dict:
    auth_params, headers = _auth()
    with httpx.Client(timeout=8.0, headers=headers) as client:
        r = client.get(f"{API}{path}", params={**(params or {}), **auth_params})
        r.raise_for_status()
        return r.json()


def _films(raw: list[dict], limit: int, newest_first: bool = False) -> list[dict]:
    """Pick by popularity, then order by DATE.

    Those are two different jobs and doing them in this order matters. TMDB
    hands back the most popular titles, which is the right way to choose WHICH
    six to show; but reading them in popularity order tells you nothing about
    when to go. So the six are chosen by popularity and then sorted
    chronologically: for anything still to come, the one that opens first is
    first, which is the order you actually plan in.

    `newest_first` flips it for films already showing, where "what just opened"
    is more useful than "what has been out longest".
    """
    # A result with no poster is reliably a listing artefact rather than a film
    # anyone will see, so those are dropped BEFORE the limit is applied —
    # otherwise they eat the slots.
    picked = [m for m in raw if m.get("poster_path")][:limit]
    picked.sort(key=lambda m: m.get("release_date") or "", reverse=newest_first)
    out = []
    for m in picked:
        out.append({
            "title": m.get("title") or m.get("original_title") or "Untitled",
            "date": m.get("release_date") or "",
            "poster": f"{IMG}{m['poster_path']}",
            "url": f"https://www.themoviedb.org/movie/{m['id']}",
            "score": round(m.get("vote_average") or 0, 1),
        })
    return out


def _series(raw: list[dict], limit: int) -> list[dict]:
    picked = [s for s in raw if s.get("poster_path")][:limit]
    picked.sort(key=lambda s: s.get("first_air_date") or "")
    out = []
    for s in picked:
        out.append({
            "title": s.get("name") or s.get("original_name") or "Untitled",
            "date": s.get("first_air_date") or "",
            "poster": f"{IMG}{s['poster_path']}",
            "url": f"https://www.themoviedb.org/tv/{s['id']}",
            "score": round(s.get("vote_average") or 0, 1),
        })
    return out


def _discover_movies(gte: str, lte: str) -> list[dict]:
    return _get("/discover/movie", {
        "region": "US",
        "language": "en-US",
        "sort_by": "popularity.desc",
        # 3 = wide theatrical. Type 2 (limited) is deliberately excluded: it is
        # most of the festival and one-cinema-in-New-York noise.
        "with_release_type": "3",
        "primary_release_date.gte": gte,
        "primary_release_date.lte": lte,
    }).get("results", [])


def releases(year: int, month: int, today: date, limit: int = 6) -> dict:
    """{'sections': [{label, entries}], 'status': 'ok'|'no_key'|'error'}

    The key is `entries`, NOT `items`: Jinja resolves `section.items` to the
    dict's built-in .items method before it looks for a key of that name, and
    the template then tries to iterate a bound method. It fails at render time
    with a TypeError that names neither the template nor the key.
    """
    if not configured():
        return {"sections": [], "status": "no_key"}

    cache_key = (year, month, today.isoformat() if (year, month) == (today.year, today.month) else "-")
    now = time.monotonic()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < TTL_SECONDS:
            return hit[1]

    last = monthrange(year, month)[1]
    month_name = _calendar.month_name[month]
    sections = []
    try:
        if (year, month) == (today.year, today.month):
            sections.append({
                "label": "In theatres now",
                "entries": _films(_get("/movie/now_playing", {"region": "US", "language": "en-US"})
                                  .get("results", []), limit, newest_first=True),
            })
            if today.day < last:
                rest = _films(_discover_movies(today.isoformat(), f"{year}-{month:02d}-{last:02d}"), 4)
                if rest:
                    sections.append({"label": f"Still to open in {month_name}", "entries": rest})
        else:
            sections.append({
                "label": f"Opening in {month_name}",
                "entries": _films(_discover_movies(f"{year}-{month:02d}-01",
                                                 f"{year}-{month:02d}-{last:02d}"), limit),
            })

        series = _series(_get("/discover/tv", {
            "language": "en-US",
            "sort_by": "popularity.desc",
            "first_air_date.gte": f"{year}-{month:02d}-01",
            "first_air_date.lte": f"{year}-{month:02d}-{last:02d}",
        }).get("results", []), 4)
        if series:
            sections.append({"label": "New series", "entries": series})

        result = {"sections": sections, "status": "ok"}
    except Exception as exc:  # noqa: BLE001 — a dead API must not break the calendar
        return {"sections": [], "status": "error", "detail": str(exc)[:200]}

    with _lock:
        _cache[cache_key] = (now, result)
    return result
