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

import pathlib
from datetime import date, timedelta
from urllib.parse import quote

from holidays import easter

# Seasons are the fallback. Northern-hemisphere naming, because that is where
# the household lives, even though half of it grew up with the opposite.
SEASONS = [
    ("winter", (12, 21), (3, 19)),
    ("spring", (3, 20), (6, 20)),
    ("summer", (6, 21), (9, 21)),
    ("fall", (9, 22), (12, 20)),
]

# Each theme is dressed by a PAINTING, not by clip-art.
#
# Every one is PUBLIC DOMAIN — old enough that copyright has lapsed — which is
# the only reason twelve full images can sit in a public repository at all.
# They are in static/art/, credited in static/art/ATTRIBUTION.md, and capped at
# 1800px and roughly half a megabyte each, because this is opened on a phone
# over a tailnet link.
#
# The choices lean moody rather than cute on purpose: Fuseli's incubus for
# Halloween, Ensor's carnival of masks, Bruegel's frozen hunters. The motifs
# survive as small accents in the rail card, where a bit of levity costs
# nothing.
THEMES = {
    "winter": {
        "art": ("winter.jpg", "Hunters in the Snow", "Pieter Bruegel the Elder", 1565),
        "name": "Winter", "accent": "#7FB2E5", "accent2": "#B8D8F0", "tint": "#0F1720",
        "motifs": ("❄️", "☃️", "\U0001F328️", "\U0001F9E3", "\U0001F3D4️", "☕"),
        "blurb": "Short days, long evenings.",
    },
    "spring": {
        "art": ("spring.jpg", "Primavera", "Sandro Botticelli", 1480),
        "name": "Spring", "accent": "#7FC8A9", "accent2": "#E9A6C4", "tint": "#101A16",
        "motifs": ("\U0001F338", "\U0001F337", "\U0001F41D", "\U0001F33F", "\U0001F326️", "\U0001F98B"),
        "blurb": "Everything starts again.",
    },
    "summer": {
        "art": ("summer.jpg", "Strolling along the Seashore", "Joaquin Sorolla", 1909),
        "name": "Summer", "accent": "#F2B33D", "accent2": "#5FC7D8", "tint": "#171408",
        "motifs": ("☀️", "\U0001F3D6️", "\U0001F576️", "\U0001F349", "\U0001F30A", "\U0001F366"),
        "blurb": "Beach weather, and the AC bill.",
    },
    "fall": {
        "art": ("fall.jpg", "Golden Autumn", "Isaac Levitan", 1895),
        "name": "Fall", "accent": "#D98E4A", "accent2": "#B5654A", "tint": "#1A1410",
        "motifs": ("\U0001F342", "\U0001F33E", "\U0001F3C8", "☕", "\U0001F343", "\U0001F9E5"),
        "blurb": "Sweater weather.",
    },
    "halloween": {
        "art": ("halloween.jpg", "The Nightmare", "Henry Fuseli", 1781),
        "name": "Halloween", "accent": "#F0821E", "accent2": "#9B6BD6", "tint": "#150E18",
        "motifs": ("\U0001F383", "\U0001F47B", "\U0001F577️", "\U0001F987", "\U0001F36C", "\U0001F56F️"),
        "blurb": "Candy, and one very good costume.",
    },
    "christmas": {
        "art": ("christmas.jpg", "The Census at Bethlehem", "Pieter Bruegel the Elder", 1566),
        "name": "Christmas", "accent": "#E5484D", "accent2": "#4FBF73", "tint": "#101812",
        "motifs": ("\U0001F384", "\U0001F381", "\U0001F385", "\U0001F98C", "\U0001F56F️", "⭐"),
        "blurb": "The good month.",
    },
    "newyear": {
        "art": ("newyear.jpg", "Fireworks at Ryogoku", "Utagawa Hiroshige", 1858),
        "name": "New Year", "accent": "#E8C33D", "accent2": "#7FB2E5", "tint": "#12131C",
        "motifs": ("\U0001F386", "\U0001F942", "\U0001F389", "\U0001F570️", "✨", "\U0001F3C1"),
        "blurb": "Reset the counters.",
    },
    "carnaval": {
        "art": ("carnaval.jpg", "Christ's Entry into Brussels in 1889", "James Ensor", 1889),
        "name": "Carnaval", "accent": "#F0459B", "accent2": "#F2C53D", "tint": "#1A0F18",
        "motifs": ("\U0001F3AD", "\U0001F941", "\U0001F483", "\U0001F3BA", "\U0001F387", "\U0001F1E7\U0001F1F7"),
        "blurb": "Brasil para.",
    },
    "easter": {
        "art": ("easter.jpg", "Almond Blossom", "Vincent van Gogh", 1890),
        "name": "Easter", "accent": "#C9A6E9", "accent2": "#8FD3B6", "tint": "#141020",
        "motifs": ("\U0001F430", "\U0001F95A", "\U0001F36B", "\U0001F337", "\U0001F423", "\U0001F338"),
        "blurb": "Chocolate season.",
    },
    "july4": {
        "art": ("july4.jpg", "Our Banner in the Sky", "Frederic Edwin Church", 1861),
        "name": "4th of July", "accent": "#4F86E5", "accent2": "#E5484D", "tint": "#0E1420",
        "motifs": ("\U0001F1FA\U0001F1F8", "\U0001F386", "\U0001F32D", "\U0001F5FD", "\U0001F389", "\U0001F35F"),
        "blurb": "Fireworks over the neighbourhood.",
    },
    "farroupilha": {
        "art": ("farroupilha.jpg", "La doma", "Juan Manuel Blanes", 1870),
        "name": "Farroupilha", "accent": "#4FBF73", "accent2": "#E8C33D", "tint": "#101A14",
        "motifs": ("\U0001F1E7\U0001F1F7", "\U0001F40E", "\U0001F969", "\U0001F9C9", "\U0001F525", "\U0001F920"),
        "blurb": "Churrasco e chimarrao.",
    },
    "thanksgiving": {
        "art": ("thanksgiving.jpg", "Sumptuous Still Life with Fruits, Pie and Goblets", "Jan Davidsz. de Heem", 1655),
        "name": "Thanksgiving", "accent": "#C97B3D", "accent2": "#D9B44A", "tint": "#181209",
        "motifs": ("\U0001F983", "\U0001F967", "\U0001F33D", "\U0001F35E", "\U0001F342", "\U0001F37D️"),
        "blurb": "Eat, then do not move.",
    },
}


def pattern_uri(motifs: tuple[str, ...]) -> str:
    """An SVG data URI tiling the theme's motifs, for the page wallpaper.

    Generated rather than shipped: a tile per theme would be twelve binary
    files to keep in step with this table, and this stays one source of truth.
    The positions are fixed, not random, so the tile seams line up.
    """
    spots = [(26, 62, 40), (128, 40, 26), (196, 108, 34),
             (58, 168, 30), (150, 196, 38), (222, 236, 28)]
    parts = []
    for i, (x, y, size) in enumerate(spots):
        parts.append(
            f"<text x='{x}' y='{y}' font-size='{size}'"
            f" transform='rotate({-18 + i * 11} {x} {y})'>{motifs[i % len(motifs)]}</text>"
        )
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='260' height='260'>"
        + "".join(parts)
        + "</svg>"
    )
    return "data:image/svg+xml," + quote(svg, safe="")


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
    month = (start + (end - start) / 2).month
    if override and override in THEMES:
        return _dress(override, auto=False, month=month)

    best: tuple[int, str] | None = None
    for year in {start.year, end.year}:
        for key, w_start, w_end, priority in special_windows(year):
            if w_start <= end and w_end >= start:
                if best is None or priority > best[0]:
                    best = (priority, key)
    key = best[1] if best else season_for(start + (end - start) / 2)
    return _dress(key, auto=True, month=month)


# The fallback picture is chosen BY MONTH, one each, never by season.
#
# It used to fall out of the theme, and that produced duplicates that read as
# a bug: March and April both landed on Easter (the 2026 window straddles the
# two), and May and June both landed on Spring (neither has an event window, so
# both fell through to the same season). Twelve months, twelve pictures, no
# arithmetic.
#
# Two entries here are used only when a theme is pinned by hand in the picker:
# newyear.jpg and fall.jpg. That is deliberate, not a leftover — January is
# better served by Bruegel's snow than by fireworks, and November by the
# Thanksgiving table than by another autumn landscape.
FALLBACK_ART = {
    1:  ("winter.jpg", "Hunters in the Snow", "Pieter Bruegel the Elder", 1565),
    2:  ("carnaval.jpg", "Christ's Entry into Brussels in 1889", "James Ensor", 1889),
    3:  ("spring.jpg", "Primavera", "Sandro Botticelli", 1480),
    4:  ("easter.jpg", "Almond Blossom", "Vincent van Gogh", 1890),
    5:  ("may.jpg", "The Artist's Garden at Giverny", "Claude Monet", 1900),
    6:  ("june.jpg", "Les Coquelicots", "Gustave Courbet", 1850),
    7:  ("july4.jpg", "Our Banner in the Sky", "Frederic Edwin Church", 1861),
    8:  ("summer.jpg", "Strolling along the Seashore", "Joaquin Sorolla", 1909),
    9:  ("farroupilha.jpg", "La doma", "Juan Manuel Blanes", 1870),
    10: ("halloween.jpg", "The Nightmare", "Henry Fuseli", 1781),
    11: ("thanksgiving.jpg", "Sumptuous Still Life with Fruits, Pie and Goblets", "Jan Davidsz. de Heem", 1655),
    12: ("christmas.jpg", "The Census at Bethlehem", "Pieter Bruegel the Elder", 1566),
}

ART_DIR = pathlib.Path("static/art")
# Willian's own images, one per month, dropped in as month-01 … month-12.
# Checked on every request rather than cached at startup: adding a picture
# should be "copy the file in and reload", not "copy it in and remember to
# restart".
MONTH_ART_EXT = ("jpg", "jpeg", "png", "webp", "avif")


def month_art(month: int) -> str | None:
    for ext in MONTH_ART_EXT:
        name = f"month-{month:02d}.{ext}"
        if (ART_DIR / name).exists():
            return name
    return None


def _dress(key: str, auto: bool, month: int | None = None) -> dict:
    t = THEMES[key]
    # Which picture, in order of precedence:
    #   1. Willian's own image for this month, if he has supplied one
    #   2. the pinned theme's painting, when a theme was chosen by hand — the
    #      picker has to change the picture or it is not really a picker
    #   3. the month's own fallback painting
    own = month_art(month) if month else None
    if own:
        art_file, art_title, art_artist, art_year = own, None, None, None
    elif not auto:
        art_file, art_title, art_artist, art_year = t["art"]
    else:
        art_file, art_title, art_artist, art_year = FALLBACK_ART[month or 1]
    return {
        "art_own": bool(own),
        "key": key,
        "auto": auto,
        # The first motif doubles as the single icon in the header brand.
        "motif": t["motifs"][0],
        "pattern": pattern_uri(t["motifs"]),
        "art_file": art_file,
        "art_title": art_title,
        "art_artist": art_artist,
        "art_year": art_year,
        **t,
    }


def theme_choices() -> list[tuple[str, str]]:
    return [(k, v["name"]) for k, v in THEMES.items()]
