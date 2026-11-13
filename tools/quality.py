"""Tracing quality on the reference pictures, against the numbers of the last release.

    QT_QPA_PLATFORM=offscreen python tools/quality.py            check (exit 1 if worse)
    QT_QPA_PLATFORM=offscreen python tools/quality.py --update   record the numbers as the new baseline

Each reference picture (tests/reference/) is traced in several modes; the SVG is drawn back at
the picture's size (by the engine's own drawing) on white and compared with the picture on
white. "Badly wrong" pixels: off by more than 64 levels (25%) in some channel. A result is
worse when it has more badly wrong pixels than the baseline by more than 0.02 percentage
points and 5% of the baseline, or takes more than 3 times as long (and over 0.5 s). The
baseline is tests/reference/quality.json; update it (with the numbers in the commit message)
only for a change that's meant to change tracing.
"""

import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

APP = QGuiApplication.instance() or QGuiApplication(["quality"])

from kanzonassvg import engine, image, tracing  # noqa: E402

REF = os.path.join(ROOT, "tests", "reference")
BASELINE = os.path.join(REF, "quality.json")
CASES = [
    # picture, label, options (None: Auto settings)
    ("logo.png", "auto", None),
    ("logo.png", "colors 8", dict(scans=8)),
    ("logo.png", "autotrace 8", dict(mode=engine.AUTOTRACE, scans=8)),
    ("logo_jpg.jpg", "auto", None),
    ("logo_alpha.png", "auto", None),
    ("smiley.png", "auto", None),
    ("smiley.png", "colors 8", dict(scans=8)),
    ("smiley.png", "autotrace 8", dict(mode=engine.AUTOTRACE, scans=8)),
    ("starry-night.jpg", "auto", None),
    ("starry-night.jpg", "colors 16", dict(scans=16)),
    ("starry-night.jpg", "autotrace 16", dict(mode=engine.AUTOTRACE, scans=16)),
    ("starry-night.jpg", "bw", dict(mode=engine.BRIGHTNESS)),
]


def on_white(img):
    out = QImage(img.width(), img.height(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.white)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def badly_wrong(a, b):
    import numpy as np
    x = np.frombuffer(a.constBits(), np.uint8).reshape(a.height(), a.bytesPerLine())[:, :a.width() * 4]
    y = np.frombuffer(b.constBits(), np.uint8).reshape(b.height(), b.bytesPerLine())[:, :b.width() * 4]
    d = np.abs(x.astype(int) - y.astype(int)).reshape(a.height(), a.width(), 4)[:, :, :3].max(axis=2)
    return float((d > 64).mean() * 100)


def measure():
    results = {}
    for name, label, opts in CASES:
        img = image.load(os.path.join(REF, name))
        t = time.perf_counter()
        options = engine.auto(*image.pixels(img))[0] if opts is None else engine.Options(**opts)
        res = tracing.trace_image(img, options)
        secs = time.perf_counter() - t
        drawn = QImage(img.width(), img.height(), QImage.Format.Format_ARGB32_Premultiplied)
        drawn.fill(Qt.GlobalColor.white)
        engine.Drawing(res.svg).render_image(drawn, 0, 0, img.width(), img.height())
        key = "%s, %s" % (name, label)
        results[key] = {"badly_wrong_pct": round(badly_wrong(on_white(img), drawn), 3), "shapes": res.shapes,
                        "kb": round(len(res.svg.encode()) / 1024), "seconds": round(secs, 3)}
        print("%-32s %7.3f%% badly wrong, %4d shapes, %6d KB, %.2f s" % (
            key, results[key]["badly_wrong_pct"], res.shapes, results[key]["kb"], secs), flush=True)
    return results


def main():
    results = measure()
    if "--update" in sys.argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, sort_keys=True)
            f.write("\n")
        print("baseline written:", BASELINE)
        return 0
    with open(BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    worse = []
    for key, now in results.items():
        was = base.get(key)
        if was is None:
            worse.append("%s: not in the baseline (run with --update)" % key)
            continue
        limit = was["badly_wrong_pct"] + max(0.02, 0.05 * was["badly_wrong_pct"])
        if now["badly_wrong_pct"] > limit:
            worse.append("%s: %.3f%% badly wrong, was %.3f%%" % (key, now["badly_wrong_pct"], was["badly_wrong_pct"]))
        if now["seconds"] > max(0.5, 3 * was["seconds"]):
            worse.append("%s: %.2f s, was %.2f s" % (key, now["seconds"], was["seconds"]))
    for w in worse:
        print("WORSE", w)
    print("quality: %s" % ("WORSE" if worse else "as good as the baseline or better"))
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main())
