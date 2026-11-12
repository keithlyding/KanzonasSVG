"""The window: open, trace, show the colors, save, copy, paste."""

import os
import tempfile
import time
import unittest

from tests import helpers  # noqa: F401
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, engine

from tests.helpers import logo


def wait(cond, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


class TestWindow(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.png = os.path.join(self.tmp.name, "logo.png")
        logo().save(self.png)
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        QApplication.processEvents()
        self.tmp.cleanup()

    def traced(self):
        return wait(lambda: self.w.worker is None and not self.w.timer.isActive() and self.w.result is not None)

    def test_open_trace_save(self):
        self.assertFalse(self.w.a_save.isEnabled())
        self.assertTrue(self.w.open_path(self.png))
        self.assertTrue(self.traced())
        self.assertEqual(self.w.result.shapes, 3)
        self.assertIn("3 shapes", self.w.status.text())
        self.assertTrue(self.w.a_save.isEnabled())
        dst = os.path.join(self.tmp.name, "out.svg")
        self.assertTrue(self.w.write(dst))
        with open(dst, encoding="utf-8") as f:
            self.assertIn("#1d3f8f", f.read())
        self.assertEqual(self.w.default_name(), os.path.splitext(self.png)[0] + ".svg")

    def test_auto_on_open_and_by_button(self):
        self.w.settings.scans.setValue(12)
        self.w.settings.smooth.setChecked(True)
        QApplication.processEvents()
        self.w.timer.stop()
        self.w.open_path(self.png)
        self.assertTrue(self.traced())
        self.assertEqual(self.w.settings.scans.value(), 3)
        self.assertFalse(self.w.settings.smooth.isChecked())
        self.assertIn("Auto: 3 colors", self.w.status.text())
        # the user's change stays; Auto again puts it back
        self.w.settings.scans.setValue(6)
        self.assertTrue(wait(lambda: self.w.worker is None and not self.w.timer.isActive()
                             and self.w.job.options.scans == 6))
        self.assertEqual(self.w.settings.scans.value(), 6)
        self.w.settings.auto.click()
        self.assertTrue(wait(lambda: self.w.worker is None and self.w.job.auto and self.w.result is not None))
        self.assertEqual(self.w.settings.scans.value(), 3)

    def test_auto_off_for_new_pictures(self):
        self.w.a_auto_new.setChecked(False)
        self.w.settings.scans.setValue(5)
        QApplication.processEvents()
        self.w.timer.stop()
        self.w.open_path(self.png)
        self.assertTrue(self.traced())
        self.assertEqual(self.w.settings.scans.value(), 5)
        self.assertNotIn("Auto", self.w.status.text())

    def test_settings_retrace(self):
        self.w.open_path(self.png)
        self.assertTrue(self.traced())
        first = self.w.result
        self.w.settings.remove_bg.setCurrentIndex(2)  # Remove, also inside
        self.assertTrue(wait(lambda: self.w.result is not first and self.w.worker is None
                             and not self.w.timer.isActive()))
        self.assertEqual(self.w.result.shapes, 2)
        # Black and white hides the color settings and shows the threshold
        self.w.settings.mode.setCurrentIndex([m for _, m in app.MODES].index(engine.BRIGHTNESS))
        self.assertFalse(self.w.settings.g_multi.isVisibleTo(self.w.settings))
        self.assertTrue(self.w.settings.g_single.isVisibleTo(self.w.settings))
        self.assertTrue(self.traced())
        wait(lambda: self.w.worker is None and not self.w.timer.isActive())
        self.assertIn("#000000", self.w.result.svg)

    def test_many_changes_end_with_the_last(self):
        self.w.open_path(self.png)
        for n in (2, 3, 4, 5, 6, 3):
            self.w.settings.scans.setValue(n)
            self.w.start_trace()
        self.assertTrue(wait(lambda: self.w.worker is None and not self.w.timer.isActive() and not self.w.pending))
        self.assertEqual(self.w.job.options.scans, 3)

    def test_show_colors(self):
        self.w.open_path(self.png)
        self.assertTrue(self.traced())
        self.w.a_colors.setChecked(True)
        self.assertTrue(wait(lambda: self.w.preview is not None and self.w.worker is None))
        self.assertIs(self.w.left.picture, self.w.preview)
        self.w.a_colors.setChecked(False)
        self.assertIs(self.w.left.picture, self.w.img)

    def test_copy_and_paste(self):
        self.w.open_path(self.png)
        self.assertTrue(self.traced())
        self.w.copy_svg()
        md = QGuiApplication.clipboard().mimeData()
        self.assertTrue(md.hasFormat("image/svg+xml") or md.text().startswith("<?xml"))
        QGuiApplication.clipboard().setImage(logo(100, 60))
        self.assertTrue(self.w.paste())
        self.assertIsNone(self.w.source_path)
        self.assertEqual(self.w.img.width(), 100)

    def test_view_zoom(self):
        self.w.open_path(self.png)
        s = self.w.view.scale
        self.w.view.zoom(2.0)
        self.assertAlmostEqual(self.w.view.scale, s * 2)
        self.w.actual_size()
        self.assertEqual(self.w.view.scale, 1.0)

    def test_help_mentions_every_menu_command(self):
        names = []
        for menu_action in self.w.menuBar().actions():
            for a in menu_action.menu().actions():
                if a.text() and not a.isSeparator():
                    names.append(a.text().replace("&", "").rstrip("."))
        for name in names:
            self.assertIn(name, app.HELP_HTML, "the help doesn't mention %r" % name)

    def test_settings_saved(self):
        self.w.settings.scans.setValue(5)
        self.w.settings.mode.setCurrentIndex(1)
        self.w.settings.save(self.w.qs)
        s2 = app.Settings()
        s2.load(self.w.qs)
        self.assertEqual(s2.scans.value(), 5)
        self.assertEqual(s2.current_mode(), engine.GRAYS)
        s2.reset_all()
        self.assertEqual(s2.scans.value(), 8)
        self.assertEqual(s2.current_mode(), engine.COLORS)


if __name__ == "__main__":
    unittest.main()
