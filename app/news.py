# "What's coming out this month" for the rail beside the calendar: theatrical
# movie releases and new series, from TMDB.
#
# Needs CAL_TMDB_KEY (free, from themoviedb.org/settings/api). WITHOUT IT THE
# RAIL SAYS SO AND THE CALENDAR IS OTHERWISE UNAFFECTED — a missing key must
# never take the calendar down, so every failure path here returns an empty
# list and a reason rather than raising.
#
# Results are cached in memory per month for 12 hours. A month's release slate
# does not change hourly, and the calendar is opened many times a day; without
# the cache every page load would be two API calls and a visible delay.

import os
import threading
import time
from calendar import monthrange
from datetime import date

import httpx

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w92"
TTL_SECONDS = 12 * 60 * 60

_cache: dict[tuple[str, int, int], tuple[float, list[dict]]] = {}
_lock = threading.Lock()


def configured() -> bool:
    return bool(os.environ.get("CAL_TMDB_KEY", "").strip())


def _auth() -> tuple[dict, dict]:
    """(extra query params, extra headers) for whichever kind of key is set.

    TMDB's settings page offers TWO credentials and it is easy to copy the
    wrong one: a short v3 "API Key" that goes in the query string, and a long
    v4 "API Read Access Token" (a JWT, starting `eyJ`) that goes in an
    Authorization header. Both are accepted here, because "I pasted the one
    that was on screen" is not a mistake worth debugging twice.
    """
    key = os.environ.get("CAL_TMDB_KEY", "").strip()
    if key.startswith("eyJ"):
        return {}, {"Authorization": f"Bearer {key}"}
    return {"api_key": key}, {}


def _get(path: str, params: dict) -> dict:
    auth_params, headers = _auth()
    with httpx.Client(timeout=8.0, headers=headers) as client:
        r = client.get(f"{API}{path}", params={**params, **auth_params})
        r.raise_for_status()
        return r.json()


def _movies(year: int, month: int, limit: int) -> list[dict]:
    last = monthrange(year, month)[1]
    data = _get(
        "/discover/movie",
        {
            "region": "US",
            "language": "en-US",
            "sort_by": "popularity.desc",
            # 3 = theatrical, 2 = limited theatrical. Excludes the long tail of
            # direct-to-streaming titles, which is the point: this rail exists
            # because of an AMC A-List subscription.
            "with_release_type": "3|2",
            "primary_release_date.gte": f"{year}-{month:02d}-01",
            "primary_release_date.lte": f"{year}-{month:02d}-{last:02d}",
            "vote_count.gte": 0,
        },
    )
    out = []
    # No poster is a reliable tell for a listing artefact rather than a film
    # anyone is going to see, so those are dropped before the limit is applied
    # instead of after — otherwise they eat the six slots.
    results = [m for m in data.get("results", []) if m.get("poster_path")]
    for m in results[:limit]:
        out.append(
            {
                "kind": "movie",
                "title": m.get("title") or m.get("original_title") or "Untitled",
                "date": m.get("release_date") or "",
                "poster": f"{IMG}{m['poster_path']}",
                "url": f"https://www.themoviedb.org/movie/{m['id']}",
                "score": round(m.get("vote_average") or 0, 1),
            }
        )
    return out


def _series(year: int, month: int, limit: int) -> list[dict]:
    last = monthrange(year, month)[1]
    data = _get(
        "/discover/tv",
        {
            "language": "en-US",
            "sort_by": "popularity.desc",
            "first_air_date.gte": f"{year}-{month:02d}-01",
            "first_air_date.lte": f"{year}-{month:02d}-{last:02d}",
        },
    )
    out = []
    results = [s for s in data.get("results", []) if s.get("poster_path")]
    for s in results[:limit]:
        out.append(
            {
                "kind": "series",
                "title": s.get("name") or s.get("original_name") or "Untitled",
                "date": s.get("first_air_date") or "",
                "poster": f"{IMG}{s['poster_path']}",
                "url": f"https://www.themoviedb.org/tv/{s['id']}",
                "score": round(s.get("vote_average") or 0, 1),
            }
        )
    return out


def releases(year: int, month: int, limit: int = 6) -> dict:
    """{'movies': [...], 'series': [...], 'status': 'ok'|'no_key'|'error'}"""
    if not configured():
        return {"movies": [], "series": [], "status": "no_key"}

    now = time.monotonic()
    with _lock:
        hit = _cache.get(("all", year, month))
        if hit and now - hit[0] < TTL_SECONDS:
            return hit[1]  # type: ignore[return-value]

    try:
        result = {
            "movies": _movies(year, month, limit),
            "series": _series(year, month, limit),
            "status": "ok",
        }
    except Exception as exc:  # noqa: BLE001 — a dead API must not break the calendar
        return {"movies": [], "series": [], "status": "error", "detail": str(exc)[:200]}

    with _lock:
        _cache[("all", year, month)] = (now, result)  # type: ignore[assignment]
    return result
