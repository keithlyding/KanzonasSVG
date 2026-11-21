"""View > Show outlines (the engine's outline drawing), File > Open recent, and Trace > Erase on
the picture (1.6)."""

import os
import tempfile
import time
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QEvent, QPointF, QRect, QSettings, Qt
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, engine
from tests.helpers import logo

SQUARE = ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
          'width="100" height="100" viewBox="0 0 100 100">\n'
          '<path style="fill:#b2002d" d="M20,20L80,20L80,80L20,80Z"/>\n</svg>\n')


def outlines(svg, nodes, size=100):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.white)
    engine.Drawing(svg).render_outlines_image(img, 0, 0, size, size, nodes)
    return img


class TestOutlineDrawing(unittest.TestCase):
    def test_lines_and_nodes(self):
        img = outlines(SQUARE, False)
        # on the outline: dark; inside and outside: white (not filled)
        self.assertLess(img.pixelColor(50, 20).lightness(), 120)
        self.assertLess(img.pixelColor(80, 50).lightness(), 120)
        self.assertEqual(img.pixelColor(50, 50).name(), "#ffffff")
        self.assertEqual(img.pixelColor(10, 10).name(), "#ffffff")
        # nodes: blue squares at the corners, only when asked for
        self.assertEqual(img.pixelColor(19, 19).name(), "#ffffff")
        with_nodes = outlines(SQUARE, True)
        c = with_nodes.pixelColor(19, 19)
        self.assertTrue(c.blue() > 200 and c.red() < 60, c.name())
        self.assertEqual(with_nodes.pixelColor(50, 50).name(), "#ffffff")

    def test_scaled_and_moved(self):
        img = QImage(300, 300, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.white)
        engine.Drawing(SQUARE).render_outlines_image(img, 50, 50, 200, 200, False)
        # the square's left side at x = 50 + 20 * 2 = 90: one pixel wide on the screen
        self.assertLess(img.pixelColor(90, 150).lightness(), 140)
        self.assertEqual(img.pixelColor(93, 150).name(), "#ffffff")
        self.assertEqual(img.pixelColor(87, 150).name(), "#ffffff")

    def test_bad_calls_are_refused(self):
        d = engine.Drawing(SQUARE)
        img = QImage(10, 10, QImage.Format.Format_ARGB32_Premultiplied)
        with self.assertRaises(engine.TraceError):
            d.render_outlines_image(img, 0, 0, 0, 10)
        with self.assertRaises(engine.TraceError):
            d.render_outlines_image(img, 0, 0, float("nan"), 10)


class WindowTest(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.w.resize(1200, 800)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def traced(self):
        end = time.time() + 30
        while time.time() < end:
            QApplication.processEvents()
            if self.w.result is not None and self.w.worker is None and not self.w.timer.isActive() \
                    and not self.w.loading():
                return True
            time.sleep(0.005)
        return False

    def opened(self, path):
        """Wait until path is the picture shown and traced (its file read in the background:
        until then the last picture's result is still there)."""
        end = time.time() + 30
        while time.time() < end and self.w.source_path != path:
            QApplication.processEvents()
            time.sleep(0.005)
        return self.w.source_path == path and self.traced()

    def drawn(self, side):
        end = time.time() + 10
        while time.time() < end:
            QApplication.processEvents()
            if side.cache is not None and side.cache[0] == side._key():
                return side.cache[1]
            time.sleep(0.005)
        self.fail("never drawn")


class TestOutlinesInTheWindow(WindowTest):
    def test_show_outlines(self):
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())
        filled = self.drawn(self.w.right)
        self.w.a_outlines.trigger()
        self.assertTrue(self.w.right.outlines)
        lines = self.drawn(self.w.right)
        self.assertNotEqual(filled, lines)
        # few nodes: shown at any zoom; many, only zoomed in
        self.assertTrue(self.w.right.show_nodes())
        self.w.right.nodes = 50000
        self.w.view.scale = 1.0
        self.assertFalse(self.w.right.show_nodes())
        self.w.view.scale = 2.0
        self.assertTrue(self.w.right.show_nodes())
        # kept for next time
        self.assertEqual(int(self.w.qs.value("view/outlines")), 1)
        self.w.a_outlines.trigger()
        self.assertFalse(self.w.right.outlines)
        self.assertEqual(int(self.w.qs.value("view/outlines")), 0)


class TestOpenRecent(WindowTest):
    def test_the_list(self):
        paths = []
        for k, name in enumerate(["a.png", "b & c.png", "d.png"]):
            p = os.path.join(self.tmp.name, name)
            logo(60 + k, 40).save(p)
            paths.append(p)
        for p in paths:
            self.assertTrue(self.w.open_path(p))
            self.assertTrue(self.opened(p))
        self.w.open_path(paths[0])              # (again: to the top, not twice)
        self.w.source_path = None
        self.assertTrue(self.opened(paths[0]))
        self.assertEqual(self.w.recent_files(), [paths[0], paths[2], paths[1]])
        self.w._fill_recent()
        texts = [a.text() for a in self.w.m_recent.actions()]
        self.assertEqual(texts[:3], ["&1 a.png", "&2 d.png", "&3 b && c.png"])
        self.assertEqual(texts[-1], "Clear the list")
        # one that's gone: said, and off the list
        os.remove(paths[2])
        shown = []
        orig = app.QMessageBox.warning
        app.QMessageBox.warning = staticmethod(lambda *a: shown.append(a[2]))
        try:
            self.assertFalse(self.w.open_recent(paths[2]))
        finally:
            app.QMessageBox.warning = orig
        self.assertIn("isn't there any more", shown[0])
        self.assertEqual(self.w.recent_files(), [paths[0], paths[1]])
        self.w.open_recent(paths[1])
        self.assertTrue(self.opened(paths[1]))
        self.w.clear_recent()
        self.w._fill_recent()
        self.assertEqual([a.text() for a in self.w.m_recent.actions()], ["No pictures yet"])

    def test_ten_at_most(self):
        for k in range(13):
            self.w.remember_recent(os.path.join(self.tmp.name, "p%d.png" % k))
        files = self.w.recent_files()
        self.assertEqual(len(files), 10)
        self.assertTrue(files[0].endswith("p12.png"))


class TestEraser(WindowTest):
    def setUp(self):
        super().setUp()
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())

    def test_erase_undo_restore(self):
        w = self.w
        first = w.result.svg
        self.assertFalse(w.a_unerase.isEnabled())
        w.a_erase.trigger()
        self.assertTrue(w.left.erase_mode)
        w.on_erased(12, [QPointF(30, 80), QPointF(80, 80)])   # across the red block
        self.assertTrue(self.traced())
        self.assertEqual(w.img.pixelColor(50, 80).alpha(), 0)
        self.assertEqual(w.full_img.pixelColor(50, 80).alpha(), 255, "the picture itself changed")
        self.assertNotEqual(w.result.svg, first)
        self.assertTrue(w.a_unerase.isEnabled())
        # the SVG shown is the trace of the erased picture
        expect = app.tracing.trace_image(w.img, w.settings.options(), w.settings.enlarge_setting()).svg
        self.assertEqual(w.result.svg, expect)
        w.undo()
        self.assertTrue(self.traced())
        self.assertEqual(w.img.pixelColor(50, 80).alpha(), 255)
        self.assertEqual(w.result.svg, first)
        w.redo()
        self.assertTrue(self.traced())
        self.assertEqual(w.img.pixelColor(50, 80).alpha(), 0)
        w.restore_picture()
        self.assertTrue(self.traced())
        self.assertEqual(w.img.pixelColor(50, 80).alpha(), 255)
        self.assertEqual(w.result.svg, first)
        # a new picture: nothing erased
        w.on_erased(12, [QPointF(50, 80)])
        self.assertTrue(self.traced())
        w.set_image(logo(), None)
        self.assertTrue(self.traced())
        self.assertEqual(w.erased, ())

    def test_with_a_crop(self):
        w = self.w
        w.crop_to(QRect(100, 20, 130, 120))            # the ring
        self.assertTrue(self.traced())
        w.start_erasing(True)
        w.on_erased(6, [QPointF(65, 60)])               # the dot in the middle, in the crop's pixels
        self.assertTrue(self.traced())
        self.assertEqual(w.erased[0][1][0], (165.0, 80.0))   # kept in the whole picture's pixels
        self.assertEqual(w.img.pixelColor(65, 60).alpha(), 0)
        w.remove_crop()
        self.assertTrue(self.traced())
        self.assertEqual(w.img.pixelColor(165, 80).alpha(), 0)
        self.assertEqual(w.img, w.picture_now())

    def test_modes_and_keys(self):
        w = self.w
        w.start_erasing(True)
        size = w.left.eraser
        w.eraser_size(1.5)
        self.assertEqual(w.left.eraser, round(size * 1.5))
        for _ in range(30):
            w.eraser_size(1.5)
        self.assertEqual(w.left.eraser, 200)
        # cropping stops erasing; Esc stops erasing
        w.start_crop()
        self.assertFalse(w.left.erase_mode)
        self.assertFalse(w.a_erase.isChecked())
        w.cancel_crop()
        w.start_erasing(True)
        w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(w.left.erase_mode)
        self.assertFalse(w.a_erase.isChecked())

    def test_dragging(self):
        # a real drag on the left side erases; a drag without erasing mode moves the picture
        from PySide6.QtTest import QTest
        w = self.w
        left = w.left
        t = w.view.target(left.size())
        a = QPointF(t.x() + 30 * w.view.scale, t.y() + 80 * w.view.scale).toPoint()
        b = QPointF(t.x() + 80 * w.view.scale, t.y() + 80 * w.view.scale).toPoint()
        w.start_erasing(True)
        QTest.mousePress(left, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
        QTest.mouseMove(left, b)
        QTest.mouseRelease(left, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
        self.assertTrue(self.traced())
        self.assertEqual(len(w.erased), 1)
        self.assertEqual(w.img.pixelColor(55, 80).alpha(), 0)


if __name__ == "__main__":
    unittest.main()
