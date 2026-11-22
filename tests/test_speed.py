"""Speed budgets: the app has to stay fast and never freeze. Each budget is several times what
it takes today (GitHub's build machines are slower than a desktop), but catches the things that
used to make it clunky: drawing SVGs while holding Python's lock (the window froze 0.3-0.9 s),
reducing the colors again for a setting that doesn't change them, tracing layers one at a time.

Today on a 4-core machine: a 12-megapixel photo traced in 1.0 s, again with another speckle size
in 0.33 s; the window's longest freeze 0.02-0.1 s; a photo's SVG drawn in 0.02-0.03 s.
"""

import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QRectF, QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, engine, image, tracing

SLACK = float(os.environ.get("KZ_SPEED_SLACK", "1"))  # more on a known-slow machine


def photo(w, h, seed=3):
    """A picture with many colors, shapes and texture (a stand-in for a photo)."""
    rng = random.Random(seed)
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(120, 140, 160))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(400):
        p.setBrush(QColor(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
        p.drawEllipse(QRectF(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(10, w / 4), rng.uniform(10, h / 4)))
    # texture: thousands of small spots, so the SVG is as detailed as a real photo's
    for _ in range(20000):
        p.setBrush(QColor(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
        p.drawEllipse(QRectF(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(3, 14), rng.uniform(3, 14)))
    p.end()
    return image.to_rgba(img)


class TestSpeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.big = photo(3000, 2000)  # 6 megapixels

    def test_trace_and_retrace(self):
        px = image.pixels(self.big)
        o = engine.Options(scans=12)
        t = time.perf_counter()
        engine.trace(*px, options=o)
        first = time.perf_counter() - t
        self.assertLess(first, 6.0 * SLACK, "6-megapixel trace: %.2f s" % first)

    def test_settings_reuse_the_colors(self):
        # The reduced colors are kept by picture and settings (AGENTS.md, "Speed"): a setting that
        # doesn't change them (Speckles) doesn't work them out again, and another number of
        # colors starts from the kept smoothed picture and histogram. Checked by the engine's own
        # report of the steps it runs (KZ_PROFILE, read once per process: so in one of its own).
        # (This was a timing ratio, retrace < 75% of the first trace: it passed here at 51-55%
        # but failed on GitHub's Windows machines now and then, a retrace once taking longer
        # than a whole first trace; the steps run say whether the colors were reused, exactly.)
        script = (
            "import sys\n"
            "from tests import test_speed as ts\n"
            "from kanzonassvg import engine, image\n"
            "px = image.pixels(ts.photo(600, 400))\n"
            "o = engine.Options(scans=12)\n"
            "for label, name, value in (('first', None, 0), ('speckles', 'speckles', 6), ('colors', 'scans', 9)):\n"
            "    if name: setattr(o, name, value)\n"
            "    print('== ' + label, file=sys.stderr, flush=True)\n"
            "    engine.trace(*px, options=o)\n")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, KZ_PROFILE="1", QT_QPA_PLATFORM="offscreen")
        run = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True,
                             timeout=300)
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])
        steps, label = {}, None
        for line in run.stderr.splitlines():
            if line.startswith("== "):
                label = line[3:]
                steps[label] = []
            elif line.startswith("kz: ") and label:
                steps[label].append(line[4:].rsplit(None, 2)[0].strip())
        self.assertIn("smooth", steps["first"], run.stderr)
        self.assertIn("quantize", steps["first"], run.stderr)
        self.assertEqual(steps["speckles"], [], "another Speckles worked the colors out again: %s" % steps)
        self.assertIn("quantize", steps["colors"], run.stderr)
        self.assertNotIn("smooth", steps["colors"], "another number of colors smoothed again: %s" % steps)
        self.assertNotIn("histogram", steps["colors"], "another number of colors counted again: %s" % steps)

    def test_drawing_an_svg(self):
        svg, _ = engine.trace(*image.pixels(self.big), options=engine.Options(scans=16))
        d = engine.Drawing(svg)
        img = QImage(1600, 1100, QImage.Format.Format_ARGB32_Premultiplied)
        best = 9.0
        for _ in range(3):
            img.fill(Qt.GlobalColor.transparent)
            t = time.perf_counter()
            d.render_image(img, 0, 0, 1600, 1066)
            best = min(best, time.perf_counter() - t)
        # this SVG (22.6 MB, the detailed test picture): 0.11 s on 4 cores, 0.26 s on one; Qt's
        # renderer took 3.6 s. (0.15 s was set before the test picture was made detailed, and a
        # slower build machine took 0.17 s.)
        self.assertLess(best, 0.45 * SLACK, "drawing the SVG: %.3f s" % best)

    def test_quick_preview_of_a_big_picture(self):
        w = app.MainWindow()
        w.show()
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_quick.png")
        self.big.save(path)
        try:
            t = time.perf_counter()
            w.open_path(path)
            quick = full = None
            end = time.time() + 120
            while time.time() < end and full is None:
                QApplication.processEvents()
                if quick is None and w.right.svg and w.result is None:
                    quick = time.perf_counter() - t
                    self.assertFalse(w.a_save.isEnabled(), "Save on before the whole picture's SVG")
                    self.assertIn("Quick preview", w.status.text())
                if w.result is not None and w.worker is None:
                    full = time.perf_counter() - t
                time.sleep(0.002)
            self.assertIsNotNone(quick, "no quick preview")
            self.assertIsNotNone(full)
            self.assertLess(quick, full, "the preview came no sooner than the SVG")
            self.assertTrue(w.a_save.isEnabled())
            self.assertNotIn("Quick preview", w.status.text())
        finally:
            w.close()
            os.remove(path)

    @staticmethod
    def solid_area():
        """A big solid area: Autotrace's centerline thinning needs a pass for each pixel from its
        edge to its middle (1,400 at 4 times this size)."""
        img = QImage(1600, 1000, QImage.Format.Format_RGBA8888)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        p.fillRect(QRectF(200, 150, 1200, 700), QColor(0, 0, 0))
        p.end()
        return img

    def test_centerline_of_a_solid_area(self):
        # Each pass went over the whole picture: minutes for this one (an hour for the app
        # battery's pictures); 3 s today
        t = time.perf_counter()
        tracing.trace_image(self.solid_area(), engine.Options(mode=engine.CENTERLINE), enlarge=4)
        took = time.perf_counter() - t
        self.assertLess(took, 20.0 * SLACK, "centerline of a solid area at 4 times: %.2f s" % took)

    def test_cancelling_centerline(self):
        # Cancel wasn't noticed while the centerline was being thinned, nor while the colors were
        # reduced (any mode: no progress reported then), and once noticed while Autotrace
        # looked for the lines, it went on to the end of the picture throwing an exception
        # for every pixel (15 s): the next trace, and closing the window, waited for it. Cancelled
        # early (colors), while thinning, and while finding the lines: each stops within 0.3 s.
        img = self.solid_area()
        for when, at in (("in the colors", 0.1), ("while thinning", 0.5), ("finding the lines", 0.3)):
            t = time.perf_counter()
            stop = [None]

            def progress(f, at=at, when=when):
                if stop[0] is None and (f >= at if when == "finding the lines" else time.perf_counter() - t > at):
                    stop[0] = time.perf_counter()
                return stop[0] is not None

            with self.assertRaises(engine.Cancelled):
                tracing.trace_image(img, engine.Options(mode=engine.CENTERLINE), enlarge=4, progress=progress)
            took = time.perf_counter() - stop[0]
            self.assertLess(took, 1.5 * SLACK, "a centerline cancelled %s went on for %.2f s" % (when, took))

    def test_window_switching_away_from_centerline(self):
        # A big picture traced as a centerline, then Colors while it was still tracing: the colors
        # waited for the whole centerline (minutes on a slow machine), and so did closing the window
        w = app.MainWindow()
        folder = tempfile.mkdtemp()
        w.qs = QSettings(os.path.join(folder, "s.ini"), QSettings.Format.IniFormat)
        w.show()
        s = w.settings
        s.mode.setCurrentIndex(s.mode.findData(engine.CENTERLINE))
        s.enlarge.setCurrentIndex(s.enlarge.findData(4))
        try:
            w.set_image(image.to_rgba(self.solid_area()), None)
            end = time.time() + 30
            while w.worker is None and time.time() < end:
                QApplication.processEvents()
                time.sleep(0.002)
            self.assertIsNotNone(w.worker, "the centerline trace didn't start")
            time.sleep(0.5)
            s.mode.setCurrentIndex(s.mode.findData(engine.COLORS))
            t = time.perf_counter()
            end = time.time() + 60
            while time.time() < end and (w.worker is not None or w.timer.isActive() or w.pending):
                QApplication.processEvents()
                time.sleep(0.002)
            took = time.perf_counter() - t
            self.assertLess(took, 6.0 * SLACK, "Colors after Centerline took %.2f s" % took)
            s.mode.setCurrentIndex(s.mode.findData(engine.CENTERLINE))
            end = time.time() + 30
            while w.worker is None and time.time() < end:
                QApplication.processEvents()
                time.sleep(0.002)
            time.sleep(0.5)
        finally:
            t = time.perf_counter()
            w.close()
            took = time.perf_counter() - t
            w.deleteLater()
            shutil.rmtree(folder, ignore_errors=True)
        self.assertLess(took, 1.5 * SLACK, "closing the window during a centerline took %.2f s" % took)

    def test_window_never_freezes(self):
        w = app.MainWindow()
        w.resize(1300, 800)
        w.show()
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_speed.png")
        self.big.save(path)
        gaps = []
        last = [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            gaps.append(now - last[0])
            last[0] = now

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(5)

        def settle(limit=60):
            end = time.time() + limit
            while time.time() < end:
                QApplication.processEvents()
                busy = w.loading() or w.worker is not None or w.timer.isActive() or w.pending
                drawn = w.right.cache is not None and w.right.cache[0][0] == w.right.content_id
                if not busy and w.result is not None and drawn:
                    return True
                time.sleep(0.002)
            return False

        try:
            last[0] = time.perf_counter()
            w.open_path(path)
            self.assertTrue(settle())
            w.settings.speckles.setValue(5)
            self.assertTrue(settle())
            for z in (2.0, 2.0, 0.3):
                w.view.zoom(z)
                for _ in range(40):
                    QApplication.processEvents()
                    time.sleep(0.003)
            worst = max(gaps[3:])  # (the first ticks include setting up)
            self.assertLess(worst, 0.25 * SLACK, "the window froze for %.2f s" % worst)
        finally:
            timer.stop()
            w.close()
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
