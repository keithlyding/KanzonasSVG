"""Crop (Trace > Crop picture, Remove crop; the command line's --crop)."""

import os
import re
import tempfile
import time
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QEvent, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, cli
from tests.helpers import logo


def wait(cond, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def svg_size(svg):
    m = re.search(r'<svg [^>]*width="(\d+)" height="(\d+)"', svg)
    return int(m.group(1)), int(m.group(2))


class TestCrop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.w.resize(1200, 800)
        self.w.show()
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        QApplication.processEvents()
        self.tmp.cleanup()

    def traced(self):
        return wait(lambda: self.w.worker is None and not self.w.timer.isActive() and self.w.result is not None)

    def drag(self, a, b):
        """Drag on the left side from picture point a to b (picture pixels)."""
        c = self.w.left
        t = self.w.view.target(c.size())
        s = self.w.view.scale
        pa = QPointF(t.x() + a[0] * s, t.y() + a[1] * s)
        pb = QPointF(t.x() + b[0] * s, t.y() + b[1] * s)
        for kind, pos in ((QEvent.Type.MouseButtonPress, pa), (QEvent.Type.MouseMove, (pa + pb) / 2),
                          (QEvent.Type.MouseMove, pb), (QEvent.Type.MouseButtonRelease, pb)):
            buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
            e = QMouseEvent(kind, pos, c.mapToGlobal(pos), Qt.MouseButton.LeftButton, buttons,
                            Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(c, e)

    def test_drag_to_crop_and_remove(self):
        w = self.w
        self.assertFalse(w.a_uncrop.isEnabled())
        w.a_crop.trigger()
        self.assertTrue(w.left.crop_mode)
        self.drag((10, 20), (100, 140))                      # around the red block
        self.assertFalse(w.left.crop_mode)
        self.assertTrue(self.traced())
        r = w.crop
        self.assertLessEqual(abs(r.x() - 10) + abs(r.y() - 20), 2, r)
        self.assertLessEqual(abs(r.width() - 90) + abs(r.height() - 120), 3, r)
        self.assertEqual((w.img.width(), w.img.height()), (r.width(), r.height()))
        self.assertEqual(svg_size(w.result.svg), (r.width(), r.height()))
        self.assertIn("#b2002d", w.result.svg)
        self.assertNotIn("#1d3f8f", w.result.svg, "the blue ring is outside the crop")
        self.assertIn("cropped to", w.status.text())
        self.assertTrue(w.a_uncrop.isEnabled())
        # a crop within the crop: in the whole picture's pixels
        w.crop_to(QRect(5, 5, 40, 40))
        self.assertTrue(self.traced())
        self.assertEqual(w.crop, QRect(r.x() + 5, r.y() + 5, 40, 40))
        self.assertEqual(w.img.pixelColor(10, 10), w.full_img.pixelColor(w.crop.x() + 10, w.crop.y() + 10))
        # the whole picture back
        w.a_uncrop.trigger()
        self.assertTrue(self.traced())
        self.assertIsNone(w.crop)
        self.assertEqual((w.img.width(), w.img.height()), (240, 160))
        self.assertIn("#1d3f8f", w.result.svg)

    def test_at_any_zoom(self):
        w = self.w
        w.view.zoom(2.7)
        w.view.move(-80, 35)
        w.start_crop()
        self.drag((160, 30), (230, 130))                     # the blue ring's right part
        self.assertTrue(self.traced())
        self.assertLessEqual(abs(w.crop.x() - 160) + abs(w.crop.y() - 30), 2, w.crop)
        self.assertIn("#1d3f8f", w.result.svg)
        self.assertNotIn("#b2002d", w.result.svg)

    def test_esc_tiny_and_outside(self):
        w = self.w
        w.start_crop()
        w.keyPressEvent(type("E", (), {"key": lambda self: Qt.Key.Key_Escape})())
        self.assertFalse(w.left.crop_mode)
        self.assertIsNone(w.crop)
        w.start_crop()
        self.drag((50, 50), (50.5, 50.5))                    # a click, not a drag
        self.assertIsNone(w.crop)
        self.assertIn("Too small", w.status.text())
        # a click right across a pixel's edge: rounded out to whole pixels it made a 2 x 2 crop
        # (on Windows, whose window put the click there): under a screen pixel moved is a click
        w.start_crop()
        self.drag((49.9, 49.9), (50.1, 50.1))
        self.assertIsNone(w.crop)
        w.start_crop()
        self.drag((-500, -500), (-400, -400))                # off the picture
        self.assertIsNone(w.crop)
        w.start_crop()
        self.drag((-50, -50), (60, 70))                      # partly off: cut to the picture
        self.assertTrue(self.traced())
        self.assertEqual((w.crop.x(), w.crop.y()), (0, 0))

    def test_a_new_picture_starts_uncropped(self):
        w = self.w
        w.crop_to(QRect(0, 0, 50, 50))
        self.assertTrue(self.traced())
        w.start_crop()
        w.set_image(logo(120, 80), None)
        self.assertFalse(w.left.crop_mode)
        self.assertIsNone(w.crop)
        self.assertFalse(w.a_uncrop.isEnabled())
        self.assertTrue(self.traced())
        self.assertEqual(w.img.width(), 120)


class TestTransparentEdge(unittest.TestCase):
    def test_transparent_pixels_are_the_background(self):
        # a part of a transparent picture whose edge is mostly a dark shape (a cropped cactus):
        # Background: Remove left the shape out as "the color around the edge"; the background
        # is the transparent pixels
        from PySide6.QtGui import QColor, QImage
        from kanzonassvg import engine, image, tracing
        img = QImage(200, 150, QImage.Format.Format_RGBA8888)
        img.fill(QColor(0, 0, 0, 0))
        for y in range(150):
            for x in range(200):
                if not (x > 150 and y > 100):                    # all but a transparent corner
                    img.setPixelColor(x, y, QColor(0x05, 0x2A, 0x10))
                if 60 <= x < 120 and 40 <= y < 100:
                    img.setPixelColor(x, y, QColor(0xF5, 0xC5, 0x10))
        img = image.to_rgba(img)
        o, _ = engine.auto(*image.pixels(img))
        self.assertTrue(o.remove_background)
        svg = tracing.trace_image(img, o).svg
        self.assertIn("#052a10", svg, "the dark shape was taken for the background")
        self.assertIn("#f5c510", svg)
        self.assertNotIn("#ffffff", svg, "the transparent corner came out white")


class TestCropCommandLine(unittest.TestCase):
    def test_crop(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.png")
            logo().save(src)
            out = os.path.join(d, "a.svg")
            self.assertEqual(cli.run([src, "-q", "--crop", "10,20,90,120", "-o", out]), 0)
            with open(out, encoding="utf-8") as f:
                svg = f.read()
            self.assertEqual(svg_size(svg), (90, 120))
            self.assertIn("#b2002d", svg)
            self.assertNotIn("#1d3f8f", svg)
            # outside the picture: an error for that file
            self.assertEqual(cli.run([src, "-q", "-f", "--crop", "500,500,10,10", "-o", out]), 1)
            with self.assertRaises(SystemExit):
                cli.run([src, "--crop", "1,2,3"])


if __name__ == "__main__":
    unittest.main()
