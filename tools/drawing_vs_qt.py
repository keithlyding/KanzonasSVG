"""The engine's SVG drawing (what the window shows) against Qt's, on the reference pictures,
every mode, fitted and zoomed in 4 times. Exit 1 if more than 0.1% of the pixels of a filled
mode are off by over 25% (centerlines thinner than a pixel are drawn a little lighter: 1%)."""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

APP = QGuiApplication.instance() or QGuiApplication(["drawing"])

from kanzonassvg import engine, image  # noqa: E402
from kanzonassvg.app import svg_renderer  # noqa: E402


def blank(w, h):
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    return img


def off(a, b):
    import numpy as np
    x = np.frombuffer(a.constBits(), np.uint8).reshape(a.height(), a.bytesPerLine())[:, :a.width() * 4]
    y = np.frombuffer(b.constBits(), np.uint8).reshape(b.height(), b.bytesPerLine())[:, :b.width() * 4]
    d = np.abs(x.astype(int) - y.astype(int)).reshape(a.height(), a.width(), 4).max(axis=2)
    return float((d > 64).mean() * 100)


def main():
    ref = os.path.join(ROOT, "tests", "reference")
    bad = 0
    for name in sorted(os.listdir(ref)):
        if not name.endswith((".png", ".jpg")):
            continue
        img = image.load(os.path.join(ref, name))
        for mode in (engine.COLORS, engine.BRIGHTNESS, engine.AUTOTRACE, engine.CENTERLINE):
            svg, _ = engine.trace(*image.pixels(img), options=engine.Options(mode=mode, scans=9))
            d = engine.Drawing(svg)
            r = svg_renderer(svg)
            for zoom in (1, 4):
                w, h = 1100, 800
                s = min(w / img.width(), h / img.height()) * 0.95 * zoom
                t = QRectF(w / 2 - img.width() * s / 2, h / 2 - img.height() * s / 2, img.width() * s, img.height() * s)
                a = blank(w, h)
                t0 = time.perf_counter()
                d.render_image(a, t.left(), t.top(), t.width(), t.height())
                ours = time.perf_counter() - t0
                b = blank(w, h)
                t0 = time.perf_counter()
                p = QPainter(b)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                r.render(p, t)
                p.end()
                qt = time.perf_counter() - t0
                pct = off(a, b)
                limit = 1.0 if mode == engine.CENTERLINE else 0.1
                flag = "FAIL " if pct > limit else ""
                bad += pct > limit
                print("%s%-17s %-10s x%d: %.3f%% pixels off by >25%%; ours %.3f s, Qt %.3f s"
                      % (flag, name, engine.MODE_NAMES[mode], zoom, pct, ours, qt), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
