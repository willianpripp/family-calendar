# The picture behind the calendar: one per month, and nothing else.
#
# This replaces the old theme engine. That engine picked a picture, an accent
# colour and a set of motifs from event windows (Halloween in late October,
# Carnaval 47 days before Easter, and so on), which was clever and wrong: with
# one image per month there is nothing left for it to decide, and its date
# arithmetic could make two months collide on the same picture. A month is a
# number between 1 and 12. That is the whole rule now.

import pathlib

ART_DIR = pathlib.Path("static/art")

# Willian's own images, dropped in as month-01 … month-12. Any of these
# extensions works; the first match wins.
MONTH_ART_EXT = ("jpg", "jpeg", "png", "webp", "avif")

# Shown for a month that has no picture of its own yet. All public domain, all
# credited in static/art/ATTRIBUTION.md. They exist so no month is ever
# undressed while the set is being collected, and each one is used by exactly
# one month so two months can never look alike.
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
    11: ("thanksgiving.jpg", "Sumptuous Still Life with Fruits, Pie and Goblets",
         "Jan Davidsz. de Heem", 1655),
    12: ("christmas.jpg", "The Census at Bethlehem", "Pieter Bruegel the Elder", 1566),
}


def own_art(month: int) -> str | None:
    """Willian's picture for this month, if he has supplied one.

    Checked on every request rather than cached at startup, so adding a picture
    is "copy the file in and reload" rather than "copy it in and remember to
    restart".
    """
    for ext in MONTH_ART_EXT:
        name = f"month-{month:02d}.{ext}"
        if (ART_DIR / name).exists():
            return name
    return None


def art_for(month: int) -> dict:
    """{file, credit} for a month. `credit` is None for Willian's own pictures,
    because captioning a family photo with a painter's name would be daft."""
    own = own_art(month)
    if own:
        return {"file": own, "credit": None}
    art_file, title, artist, year = FALLBACK_ART[month]
    return {"file": art_file, "credit": f"{title} — {artist}, {year}"}
