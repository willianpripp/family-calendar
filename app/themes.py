# Seasonal dress-up for the calendar.
#
# The theme follows WHAT YOU ARE LOOKING AT, not what today is: browsing to
# December in July shows the Christmas theme. That is the point — the dressing
# is a cue for where you are in the year, so tying it to the wall clock would
# make it useless while planning ahead.
#
# Each theme only overrides color tokens and adds a motif; the layout never
# changes. That keeps the fun from costing legibility, and it means a new theme
# is a dict entry rather than a stylesheet.

from datetime import date, timedelta

from holidays import easter

# Seasons are the fallback. Northern-hemisphere naming, because that is where
# the household lives, even though half of it grew up with the opposite.
SEASONS = [
    ("winter", (12, 21), (3, 19)),
    ("spring", (3, 20), (6, 20)),
    ("summer", (6, 21), (9, 21)),
    ("fall", (9, 22), (12, 20)),
]

THEMES = {
    "winter":   {"name": "Winter",      "motif": "❄️", "accent": "#7FB2E5", "accent2": "#B8D8F0", "tint": "#0F1720"},
    "spring":   {"name": "Spring",      "motif": "\U0001F338", "accent": "#7FC8A9", "accent2": "#E9A6C4", "tint": "#101A16"},
    "summer":   {"name": "Summer",      "motif": "☀️", "accent": "#F2B33D", "accent2": "#5FC7D8", "tint": "#171408"},
    "fall":     {"name": "Fall",        "motif": "\U0001F342", "accent": "#D98E4A", "accent2": "#B5654A", "tint": "#1A1410"},
    "halloween":{"name": "Halloween",   "motif": "\U0001F383", "accent": "#F0821E", "accent2": "#9B6BD6", "tint": "#150E18"},
    "christmas":{"name": "Christmas",   "motif": "\U0001F384", "accent": "#E5484D", "accent2": "#4FBF73", "tint": "#101812"},
    "newyear":  {"name": "New Year",    "motif": "\U0001F386", "accent": "#E8C33D", "accent2": "#7FB2E5", "tint": "#12131C"},
    "carnaval": {"name": "Carnaval",    "motif": "\U0001F3AD", "accent": "#F0459B", "accent2": "#F2C53D", "tint": "#1A0F18"},
    "easter":   {"name": "Easter",      "motif": "\U0001F430", "accent": "#C9A6E9", "accent2": "#8FD3B6", "tint": "#141020"},
    "july4":    {"name": "4th of July", "motif": "\U0001F1FA\U0001F1F8", "accent": "#4F86E5", "accent2": "#E5484D", "tint": "#0E1420"},
    "farroupilha": {"name": "Farroupilha", "motif": "\U0001F1E7\U0001F1F7", "accent": "#4FBF73", "accent2": "#E8C33D", "tint": "#101A14"},
    "thanksgiving": {"name": "Thanksgiving", "motif": "\U0001F983", "accent": "#C97B3D", "accent2": "#D9B44A", "tint": "#181209"},
}


def _span(y: int, m1: int, d1: int, m2: int, d2: int) -> tuple[date, date]:
    return date(y, m1, d1), date(y, m2, d2)


def special_windows(year: int) -> list[tuple[str, date, date, int]]:
    """(theme, start, end, priority) for the dated dress-up windows.

    Higher priority wins when two windows land in the same view. Halloween
    beats fall in October; Christmas beats winter in December.
    """
    e = easter(year)
    carn = e - timedelta(days=47)
    return [
        ("newyear", date(year, 12, 27), date(year, 12, 31), 30),
        ("newyear", date(year, 1, 1), date(year, 1, 2), 30),
        ("carnaval", carn - timedelta(days=3), carn + timedelta(days=2), 40),
        ("easter", e - timedelta(days=7), e + timedelta(days=1), 25),
        ("july4", date(year, 7, 1), date(year, 7, 7), 30),
        ("farroupilha", date(year, 9, 17), date(year, 9, 22), 30),
        ("halloween", date(year, 10, 10), date(year, 10, 31), 35),
        ("thanksgiving", date(year, 11, 18), date(year, 11, 30), 30),
        ("christmas", date(year, 12, 1), date(year, 12, 26), 35),
    ]


def season_for(d: date) -> str:
    for name, (m1, d1), (m2, d2) in SEASONS:
        start, end = date(d.year, m1, d1), date(d.year, m2, d2)
        if start > end:  # winter wraps the new year
            if d >= start or d <= date(d.year, m2, d2):
                return name
        elif start <= d <= end:
            return name
    return "winter"


def theme_for(start: date, end: date, override: str | None = None) -> dict:
    """The theme for a visible date range: a month grid, or a week.

    A special window only has to INTERSECT the range, so opening October at all
    is enough to get pumpkins, rather than needing the 31st on screen.
    """
    if override and override in THEMES:
        return {"key": override, "auto": False, **THEMES[override]}

    best: tuple[int, str] | None = None
    for year in {start.year, end.year}:
        for key, w_start, w_end, priority in special_windows(year):
            if w_start <= end and w_end >= start:
                if best is None or priority > best[0]:
                    best = (priority, key)
    key = best[1] if best else season_for(start + (end - start) / 2)
    return {"key": key, "auto": True, **THEMES[key]}


def theme_choices() -> list[tuple[str, str]]:
    return [(k, v["name"]) for k, v in THEMES.items()]
