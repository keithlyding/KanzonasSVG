"""The README's screenshots (docs/screenshot*.png), made by the app itself: a picture opened
with fresh settings (Auto settings for new pictures, as on a first start), traced, and the
window captured at 1400 x 820. Run it again when the window changes:

    QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py

- docs/screenshot.png: the owner's sunflower and cactus (assets/kanzonas-mark-source.png).
- docs/screenshot-colors.png: the same, with its colors edited in the Colors box.
- docs/screenshot-landscape.png: a flat illustration drawn here (tools/make_screenshots.py's
  own landscape(), so no one else's picture), in many colors.
"""

import os
import sys
from math import cos, pi, sin
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPolygonF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SETTINGS = tempfile.mkdtemp(prefix="kzsvg-shots")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS)
APP = QApplication.instance() or QApplication(["KanzonasSVG"])
APP.setOrganizationName("Kanzonas")
APP.setApplicationName("KanzonasSVG")

from kanzonassvg import app  # noqa: E402

W, H = 1400, 820


def landscape(path, w=900, h=640):
    """A flat illustration: sky, sun, hills, a lake, pines, a house with a red roof, flowers,
    in 15 colors."""
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor("#8fd3f4"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillRect(QRectF(0, 0, w, h * 0.62), QColor("#ffc46b"))
    p.setBrush(QColor("#fff3b0"))
    p.drawEllipse(QPointF(w * 0.72, h * 0.25), 70, 70)
    p.setBrush(QColor("#ffe066"))
    p.drawEllipse(QPointF(w * 0.72, h * 0.25), 52, 52)

    def hill(color, pts):
        path = QPainterPath(QPointF(0, h))
        for x, y in pts:
            path.lineTo(QPointF(x * w, y * h))
        path.lineTo(QPointF(w, h))
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)

    hill("#7b5ea7", [(0, 0.42), (0.18, 0.28), (0.36, 0.45), (0.55, 0.30), (0.78, 0.48), (1, 0.36)])
    hill("#4f8a5b", [(0, 0.56), (0.25, 0.47), (0.5, 0.58), (0.75, 0.50), (1, 0.57)])
    p.setBrush(QColor("#2f9fd8"))
    p.drawRect(QRectF(0, h * 0.62, w, h * 0.12))
    p.setBrush(QColor("#fff3b0"))
    for x in (0.15, 0.45, 0.8):
        p.drawRoundedRect(QRectF(w * x, h * 0.66, 90, 6), 3, 3)
    p.setBrush(QColor("#6abf4b"))
    p.drawRect(QRectF(0, h * 0.74, w, h * 0.26))
    for x, s in ((0.08, 1.0), (0.17, 0.8), (0.86, 1.1), (0.94, 0.85)):
        p.setBrush(QColor("#6b3e26"))
        p.drawRect(QRectF(w * x - 8 * s, h * 0.86, 16 * s, 40 * s))
        p.setBrush(QColor("#1f6b3a"))
        for k in range(3):
            top = h * 0.86 - (60 + 45 * k) * s
            p.drawPolygon(QPolygonF([QPointF(w * x, top), QPointF(w * x - (55 - 12 * k) * s, top + 75 * s),
                                     QPointF(w * x + (55 - 12 * k) * s, top + 75 * s)]))
    # the house
    p.setBrush(QColor("#f4e3c1"))
    p.drawRect(QRectF(w * 0.38, h * 0.70, 200, 130))
    p.setBrush(QColor("#d63c3c"))
    p.drawPolygon(QPolygonF([QPointF(w * 0.38 - 25, h * 0.70), QPointF(w * 0.38 + 100, h * 0.70 - 90),
                             QPointF(w * 0.38 + 225, h * 0.70)]))
    p.setBrush(QColor("#2e5aa8"))
    p.drawRect(QRectF(w * 0.38 + 80, h * 0.70 + 55, 40, 75))
    p.setBrush(QColor("#ffe066"))
    for x in (25, 140):
        p.drawRect(QRectF(w * 0.38 + x, h * 0.70 + 30, 36, 32))
    # flowers in the grass
    for k in range(11):
        x, y = w * (0.05 + 0.088 * k), h * (0.82 + 0.07 * (k % 2))
        if 0.36 < x / w < 0.62 and y < h * 0.92:
            continue                    # (not on the house)
        p.setBrush(QColor(["#ff5fa2", "#ff7b00", "#ffe066", "#b388ff"][k % 4]))
        for a in range(5):
            p.drawEllipse(QPointF(x + 11 * cos(a * 2 * pi / 5), y + 11 * sin(a * 2 * pi / 5)), 9, 9)
        p.setBrush(QColor("#7b5ea7") if k % 4 != 3 else QColor("#ffe066"))
        p.drawEllipse(QPointF(x, y), 7, 7)
    p.end()
    img.save(path)


def settle(w):
    end = time.time() + 120
    while time.time() < end:
        APP.processEvents()
        drawn = w.right.cache is not None and w.right.cache[0][0] == w.right.content_id
        if not w.loading() and w.worker is None and not w.timer.isActive() and w.result is not None and drawn:
            break
        time.sleep(0.01)
    for _ in range(30):
        APP.processEvents()
        time.sleep(0.01)


def evening(w):
    """For the colors screenshot: the sky traced blue, the two darker greens merged, the roof
    slate, and the sun's swatch selected."""
    c = w.settings.colors

    def group(rgb):
        return next(g for g in c.groups if g.color == rgb)
    c.selected = set(group((0xFF, 0xC4, 0x6B)).members)
    c.change_color((0x6F, 0xA8, 0xDC))
    settle(w)
    c.selected = set(group((0x1F, 0x6B, 0x3A)).members) | set(group((0x4F, 0x8A, 0x5B)).members)
    c.merge()
    settle(w)
    c.selected = set(group((0xD6, 0x3C, 0x3C)).members)
    c.change_color((0x5A, 0x63, 0x70))
    settle(w)
    c.selected = set(group((0xFF, 0xE0, 0x66)).members)
    c._rebuild()


def shoot(picture, out, then=None):
    w = app.MainWindow()
    w.resize(W, H)
    w.show()
    w.open_path(picture)
    settle(w)
    if then is not None:
        then(w)
        settle(w)
    shot = w.grab()
    assert shot.width() == W and shot.height() == H, (shot.width(), shot.height())
    shot.save(out)
    print("%s: %s" % (out, w.status.text()))
    w.close()


def main():
    docs = os.path.join(ROOT, "docs")
    shoot(os.path.join(ROOT, "assets", "kanzonas-mark-source.png"), os.path.join(docs, "screenshot.png"))
    pic = os.path.join(SETTINGS, "landscape.png")
    landscape(pic)
    shoot(pic, os.path.join(docs, "screenshot-landscape.png"))
    shoot(pic, os.path.join(docs, "screenshot-colors.png"), evening)
    return 0


if __name__ == "__main__":
    sys.exit(main())
