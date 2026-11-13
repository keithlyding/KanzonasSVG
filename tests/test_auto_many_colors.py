"""Auto settings on flat pictures with more than 16 colors (illustrations, maps, charts): they
get their colors, up to 64, exactly; before 1.1.1 Auto stopped at 16, took them for a photo
and picked 14 or 15. Photos and paintings are picked for as before (tools/quality.py checks
the reference pictures, unchanged)."""

import random
import re
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from kanzonassvg import engine, image, tracing


def flat_picture(n, seed=1, w=900, h=640):
    """n clearly different flat colors: a background and n-1 shapes, none covering another."""
    rng = random.Random(seed)
    cols = []
    while len(cols) < n:
        c = QColor.fromHsv(rng.randrange(360), rng.randrange(80, 256), rng.randrange(60, 256))
        if all(max(abs(c.red() - d.red()), abs(c.green() - d.green()), abs(c.blue() - d.blue())) > 40 for d in cols):
            cols.append(c)
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(cols[0])
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    per_row = 10                        # (up to 70 shapes fit)
    for i, c in enumerate(cols[1:]):
        p.setBrush(c)
        x, y = 15 + (i % per_row) * 88, 15 + (i // per_row) * 88
        if i % 2:
            p.drawEllipse(QRectF(x, y, 78, 78))
        else:
            p.drawRect(QRectF(x, y, 78, 78))
    p.end()
    return image.to_rgba(img), ["#%02x%02x%02x" % (c.red(), c.green(), c.blue()) for c in cols]


def gradient_picture(w=600, h=400):
    """Smooth, clean color gradients: no flat colors to count (like a clean digital painting)."""
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    for y in range(h):
        for x in range(0, w):
            img.setPixelColor(x, y, QColor(int(255 * x / w), int(255 * y / h), int(255 * (1 - x / w) * (y / h))))
    return image.to_rgba(img)


class TestAutoManyColors(unittest.TestCase):
    def test_flat_pictures_get_their_colors(self):
        for n in (12, 20, 30, 45):
            img, cols = flat_picture(n, seed=n)
            o, info = engine.auto(*image.pixels(img))
            # (the quantizer may need a slot or two more to keep every color apart)
            self.assertTrue(n <= o.scans <= n + 2, "%d colors: Auto picked %d" % (n, o.scans))
            self.assertFalse(info.photo, "%d flat colors taken for a photo" % n)
            fills = set(re.findall(r"fill:(#[0-9a-f]{6})", tracing.trace_image(img, o).svg))
            missing = [c for c in cols if c not in fills]
            self.assertFalse(missing, "%d colors: not exact in the SVG: %s" % (n, missing))

    def test_too_many_for_auto(self):
        # over 64 flat colors (the most the window's setting takes): treated as before
        img, _ = flat_picture(70, seed=3)
        o, info = engine.auto(*image.pixels(img))
        self.assertTrue(info.photo)
        self.assertLessEqual(o.scans, 16)

    def test_gradients_are_not_flat(self):
        o, info = engine.auto(*image.pixels(gradient_picture()))
        self.assertTrue(info.photo)
        self.assertLessEqual(o.scans, 16)


if __name__ == "__main__":
    unittest.main()
