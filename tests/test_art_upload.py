# app/art.save_month_art on a tiny generated image: exercises the Pillow path
# (open, exif_transpose, LANCZOS resize, alpha_composite, JPEG save) with no
# network and no fixtures. Written for the Pillow major upgrade.

import io
import pathlib
import sys

import pytest
from PIL import Image

APP_DIR = pathlib.Path(__file__).parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import art  # noqa: E402


def _png(size, mode="RGBA", color=(200, 30, 30, 128)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, "PNG")
    return buf.getvalue()


def test_save_month_art_resizes_flattens_and_writes_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(art, "ART_DIR", tmp_path)
    wide = art.MAX_WIDTH + 400
    name = art.save_month_art(3, None, _png((wide, 100)))

    assert name == "month-03.jpg"
    with Image.open(tmp_path / name) as out:
        assert out.format == "JPEG"
        assert out.mode == "RGB"
        assert out.width == art.MAX_WIDTH


def test_save_month_art_applies_exif_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(art, "ART_DIR", tmp_path)
    img = Image.new("RGB", (80, 40), (10, 200, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to display
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)

    name = art.save_month_art(4, "willian", buf.getvalue())

    with Image.open(tmp_path / name) as out:
        assert (out.width, out.height) == (40, 80)


def test_save_month_art_rejects_non_image(tmp_path, monkeypatch):
    monkeypatch.setattr(art, "ART_DIR", tmp_path)
    with pytest.raises(art.ArtError):
        art.save_month_art(5, None, b"not an image at all")
