"""Many pictures at once (File > Convert many pictures...): the dialog, the work in the
background, and the files it saves (the same as opening each picture and saving it)."""

import os
import tempfile
import time
import unittest
from dataclasses import replace

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, batch, engine, export, image, tracing
from tests.helpers import logo


def wait_for(cond, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


class TestBatch(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.pics = []
        for name, (w, h) in (("a.png", (240, 160)), ("b.png", (120, 80)), ("c.jpg", (300, 200))):
            path = os.path.join(self.dir, name)
            self.assertTrue(logo(w, h).save(path))
            self.pics.append(path)
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.dir, "s.ini"), QSettings.Format.IniFormat)
        self.w.show()

    def tearDown(self):
        if self.w.batch is not None:
            self.w.batch.close()
        self.w.close()
        self.tmp.cleanup()

    def dialog(self, files):
        d = self.w.convert_many(files)
        QApplication.processEvents()
        return d

    def run_it(self, d):
        d.start()
        self.assertTrue(wait_for(lambda: d.worker is None), "never finished")

    def test_auto_gives_what_opening_each_gives(self):
        d = self.dialog(self.pics)
        self.assertEqual(d.files(), self.pics)
        self.assertTrue(d.r_auto.isChecked())
        self.run_it(d)
        self.assertEqual(d.summary.text(), "Saved 3 of 3.")
        for p in self.pics:
            out = os.path.splitext(p)[0] + ".svg"
            with open(out, encoding="utf-8") as f:
                saved = f.read()
            # the window, opening the picture (Auto settings for new pictures) and saving it
            self.w.open_path(p)
            self.assertTrue(wait_for(lambda: self.w.result is not None and self.w.worker is None
                                     and not self.w.loading() and not self.w.timer.isActive()))
            self.assertEqual(saved, self.w.result.svg, os.path.basename(p))
            self.w.result = None
        for i in range(3):
            self.assertIn("saved ", d.list.item(i).text())
            self.assertIn(" nodes", d.list.item(i).text())

    def test_settings_shown_and_a_format_in_a_folder(self):
        s = self.w.settings
        s.scans.setValue(2)
        s.size_unit.setCurrentIndex(s.size_unit.findData(export.MM))
        s.size_width.setValue(50)
        d = self.dialog(self.pics)
        d.r_shown.setChecked(True)
        d.format.setCurrentIndex(d.format.findData("dxf"))
        folder = os.path.join(self.dir, "out", "dxfs")          # (made when it isn't there)
        d.where.setCurrentIndex(1)
        d.folder.setText(folder)
        self.run_it(d)
        self.assertEqual(sorted(os.listdir(folder)), ["a.dxf", "b.dxf", "c.dxf"])
        o = replace(s.options(), edits=())
        for p in self.pics:
            expect = export.render(tracing.trace_image(image.load(p), o, s.enlarge_setting()).svg, "dxf",
                                   export.Size(export.MM, 50))
            with open(os.path.join(folder, os.path.splitext(os.path.basename(p))[0] + ".dxf"), "rb") as f:
                self.assertEqual(f.read(), expect)
        self.assertIn("50 mm wide", d.size_label.text())
        # remembered for next time
        self.assertEqual(self.w.qs.value("batch/format"), "dxf")
        self.assertEqual(self.w.qs.value("batch/folder"), folder)

    def test_files_already_there_and_broken_ones(self):
        broken = os.path.join(self.dir, "broken.png")
        with open(broken, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nnot a picture")
        there = os.path.splitext(self.pics[0])[0] + ".svg"
        with open(there, "w") as f:
            f.write("mine")
        d = self.dialog([self.pics[0], broken, self.pics[1]])
        self.run_it(d)
        with open(there) as f:
            self.assertEqual(f.read(), "mine", "replaced without asking")
        self.assertIn("skipped", d.list.item(0).text())
        self.assertIn("failed", d.list.item(1).text())
        self.assertIn("saved", d.list.item(2).text())
        self.assertEqual(d.summary.text(), "Saved 1 of 3; 2 not (see the list).")
        d.replace.setChecked(True)
        self.run_it(d)
        with open(there) as f:
            self.assertTrue(f.read().startswith("<?xml"))

    def test_the_list(self):
        sub = os.path.join(self.dir, "sub")
        os.mkdir(sub)
        for n in ("x.png", "y.JPG"):
            logo(60, 40).save(os.path.join(sub, n))
        for n in ("made.svg", "notes.txt"):
            with open(os.path.join(sub, n), "w") as f:
                f.write("x")
        d = self.dialog([self.pics[0], self.pics[0], sub, os.path.join(self.dir, "gone.png")])
        self.assertEqual(d.files(), [self.pics[0], os.path.join(sub, "x.png"), os.path.join(sub, "y.JPG")])
        d.list.item(0).setSelected(True)
        d.remove_selected()
        self.assertEqual(len(d.files()), 2)
        d.clear()
        self.assertFalse(d.b_start.isEnabled())
        self.assertEqual(d.summary.text(), "No pictures yet.")
        # opening it again adds to the same dialog
        self.assertIs(self.dialog([self.pics[1]]), d)
        self.assertEqual(d.files(), [self.pics[1]])

    def test_stop_and_close(self):
        big = []
        for k in range(4):
            path = os.path.join(self.dir, "big%d.png" % k)
            helpers.canvas(2600, 1800).save(path)
            big.append(path)
        d = self.dialog(big)
        d.r_shown.setChecked(True)
        self.w.settings.scans.setValue(40)
        d.start()
        self.assertTrue(wait_for(lambda: len(d.results) >= 1 or d.worker is None))
        d.stop()
        self.assertTrue(wait_for(lambda: d.worker is None))
        self.assertLess(sum(1 for ok, _t in d.results.values() if ok), 4)
        self.assertIn("stopped", d.summary.text())
        # buttons back, and closing the window while converting stops it
        self.assertTrue(d.b_start.isEnabled())
        d.replace.setChecked(True)
        d.start()
        self.w.close()
        self.assertIsNone(d.worker)

    def test_stopped_before_any_picture_says_so(self):
        # (the app battery: the summary went back to "3 pictures", as if nothing had run)
        d = self.dialog(self.pics)
        d.start()
        d.stop()            # (before the worker's first picture is done)
        self.assertTrue(wait_for(lambda: d.worker is None))
        done = sum(1 for ok, _t in d.results.values() if ok)
        self.assertEqual(d.summary.text(), "Saved %d of 3%s; stopped." % (
            done, "; %d not (see the list)" % (len(d.results) - done) if len(d.results) > done else ""))

    def test_dropping_several_pictures_opens_it(self):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(p) for p in self.pics[:2]])
        e = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, md, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)
        self.w.dropEvent(e)
        self.assertIsNotNone(self.w.batch)
        self.assertEqual(self.w.batch.files(), self.pics[:2])
        self.assertIsNone(self.w.result)        # (not opened in the window)

    def test_convert(self):
        dst = os.path.join(self.dir, "a.pdf")
        res = batch.convert(self.pics[0], dst, "pdf", export.PIXELS)
        self.assertGreater(res.nodes, 0)
        with open(dst, "rb") as f:
            self.assertEqual(f.read(), export.render(res.svg, "pdf"))
        with self.assertRaises(engine.Cancelled):
            batch.convert(self.pics[0], dst, "svg", export.PIXELS, engine.Options(), 1, lambda _f: True)


if __name__ == "__main__":
    unittest.main()
