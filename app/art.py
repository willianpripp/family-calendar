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

# Their own images, dropped in as month-01 … month-12, either at the top level
# (shared by everyone) or inside a person's folder: static/art/willian/,
# static/art/aline/. Any of these extensions works; the first match wins.
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


def own_art(month: int, person: str | None = None) -> str | None:
    """The supplied picture for this month, if there is one.

    With a person, looks in that person's folder first: `art/aline/month-05.jpg`
    beats `art/month-05.jpg`, which beats the painting. The shared level in the
    middle is the useful part of the arrangement, because it means a month
    neither of them has covered still looks deliberate rather than falling all
    the way back to a Bruegel.

    Checked on every request rather than cached at startup, so adding a picture
    is "copy the file in and reload" rather than "copy it in and remember to
    restart".
    """
    folders = [f"{person}/"] if person else []
    folders.append("")
    for folder in folders:
        for ext in MONTH_ART_EXT:
            name = f"{folder}month-{month:02d}.{ext}"
            if (ART_DIR / name).exists():
                return name
    return None


def _version(name: str) -> str:
    """A cache-busting token for one picture, from its own mtime and size.

    The global asset hash cannot do this job any more. Uploading a new picture
    for October writes month-10.jpg again: same URL, same filename, and with a
    hash computed once at startup, the same version too. The browser would keep
    showing the old one and the upload would look broken. Per-file, computed per
    request, is the only version that changes when the bytes do.
    """
    try:
        st = (ART_DIR / name).stat()
    except OSError:
        return "0"
    return f"{int(st.st_mtime)}-{st.st_size}"


def art_for(month: int, person: str | None = None) -> dict:
    """{file, credit, v} for a month. `credit` is None for their own pictures,
    because captioning a family photo with a painter's name would be daft."""
    own = own_art(month, person)
    if own:
        return {"file": own, "credit": None, "v": _version(own), "mine": True}
    art_file, title, artist, year = FALLBACK_ART[month]
    return {
        "file": art_file,
        "credit": f"{title} — {artist}, {year}",
        "v": _version(art_file),
        "mine": False,
    }


# --- accepting a picture from the browser -------------------------------------

# What the file input offers and what we agree to decode. Deliberately short:
# these three cover every phone and every screenshot, and a shorter list is a
# smaller thing to be wrong about.
ACCEPTED = ("image/jpeg", "image/png", "image/webp")
ACCEPT_ATTR = ",".join(ACCEPTED)

# Wider than this buys nothing on a 2560px monitor and costs load time on a
# phone over the tailnet.
MAX_WIDTH = 2560
# Refused before decoding. A background is a few hundred KB once re-encoded;
# anything past this is a mistake, usually a video.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class ArtError(Exception):
    """Something the person can fix, phrased for them rather than for a log."""


def save_month_art(month: int, person: str | None, data: bytes) -> str:
    """Re-encode `data` as this month's picture and return the stored name.

    The upload is never stored as sent. It is decoded, rotated upright, scaled
    down if oversized, and written as JPEG. That is three things at once:
    it proves the bytes really are an image rather than something renamed to
    .jpg, it turns a 6 MB phone photo into something that loads over a tailnet,
    and re-encoding drops the EXIF, which on a phone photo includes the GPS
    coordinates of wherever it was taken.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(data) > MAX_UPLOAD_BYTES:
        raise ArtError("That file is bigger than 25 MB. Is it a video?")

    import io

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except UnidentifiedImageError:
        raise ArtError("That does not look like a JPEG, PNG or WebP image.") from None
    except Exception:
        raise ArtError("That image could not be read. Try re-saving it as a JPEG.") from None

    # Phone photos carry their rotation in EXIF rather than in the pixels; without
    # this a portrait shot arrives on its side.
    img = ImageOps.exif_transpose(img)
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)),
                         Image.LANCZOS)
    # A background has nothing behind it, so transparency has to resolve to
    # something. Flattening onto the page's own dark ground avoids the white
    # halo that RGB conversion would otherwise leave around a transparent PNG.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        ground = Image.new("RGBA", img.size, (11, 15, 20, 255))
        img = Image.alpha_composite(ground, img)
    img = img.convert("RGB")

    folder = ART_DIR / person if person else ART_DIR
    folder.mkdir(parents=True, exist_ok=True)

    # Clear every other extension for this month first. Otherwise an old
    # month-10.png keeps winning over the month-10.jpg just written, because
    # own_art takes the first extension that matches.
    stem = f"month-{month:02d}"
    for ext in MONTH_ART_EXT:
        stale = folder / f"{stem}.{ext}"
        if stale.exists():
            stale.unlink()

    dest = folder / f"{stem}.jpg"
    img.save(dest, "JPEG", quality=85, optimize=True, progressive=True)
    return str(dest.relative_to(ART_DIR))


def remove_month_art(month: int, person: str | None) -> bool:
    """Drop this month's picture at one level, revealing whatever is beneath:
    a person's own picture gives way to the shared one, the shared one to the
    painting. Never touches the paintings themselves."""
    folder = ART_DIR / person if person else ART_DIR
    removed = False
    for ext in MONTH_ART_EXT:
        target = folder / f"month-{month:02d}.{ext}"
        if target.exists():
            target.unlink()
            removed = True
    return removed
