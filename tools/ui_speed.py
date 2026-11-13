"""The window's speed: open a picture, change a setting, zoom and move. Prints how long until
the SVG is shown and the longest time the window was frozen (a timer ticks every 5 ms; the
longest gap between ticks). Exit 1 if a freeze was longer than --max-freeze seconds.

    QT_QPA_PLATFORM=offscreen python tools/ui_speed.py PICTURE... [--max-freeze 0.25]
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication(["ui-speed"])

from kanzonassvg import app  # noqa: E402


def main():
    a = argparse.ArgumentParser()
    a.add_argument("pictures", nargs="+")
    a.add_argument("--max-freeze", type=float, default=0.25)
    args = a.parse_args()
    t0 = time.perf_counter()
    gaps, last = [], [time.perf_counter()]

    def tick():
        now = time.perf_counter()
        gaps.append(now - last[0])
        last[0] = now

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(5)
    w = app.MainWindow()
    w.resize(1400, 850)
    w.show()
    print("window open in %.2f s" % (time.perf_counter() - t0))

    def shown(limit=300):
        t = time.perf_counter()
        while time.perf_counter() - t < limit:
            APP.processEvents()
            busy = w.loading() or w.worker is not None or w.timer.isActive() or w.pending
            drawn = w.right.cache is not None and w.right.cache[0][0] == w.right.content_id and \
                w.right.cache[0][1:] == w.right._key()[1:]
            if not busy and w.result is not None and drawn:
                return time.perf_counter() - t
            time.sleep(0.002)
        return float("inf")

    def worst():
        g = max(gaps) if gaps else 0.0
        gaps.clear()
        last[0] = time.perf_counter()
        return g

    freezes = []
    for path in args.pictures:
        worst()
        w.open_path(path)
        d = shown()
        f = worst()
        freezes.append(f)
        print("%s: opened, traced and shown in %.2f s, longest freeze %.3f s (%s)"
              % (os.path.basename(path), d, f, w.status.text()))
        w.settings.speckles.setValue(w.settings.speckles.value() + 1)
        d = shown()
        f = worst()
        freezes.append(f)
        print("   another speckle size, shown in %.2f s, longest freeze %.3f s" % (d, f))
        for z in (2.0, 2.0, 0.25):
            w.view.zoom(z)
            for _ in range(60):
                APP.processEvents()
                time.sleep(0.005)
            f = worst()
            freezes.append(f)
            print("   zoom x%s: longest freeze %.3f s" % (z, f))
        w.view.move(300, 200)
        for _ in range(60):
            APP.processEvents()
            time.sleep(0.005)
        f = worst()
        freezes.append(f)
        print("   move: longest freeze %.3f s" % f)
    timer.stop()
    w.close()
    print("longest freeze overall %.3f s (limit %.2f s)" % (max(freezes), args.max_freeze))
    return 1 if max(freezes) > args.max_freeze else 0


if __name__ == "__main__":
    sys.exit(main())
