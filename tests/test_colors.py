"""Editing colors (1.2): the engine's color edits and palette, the Colors box, the command line."""

import io
import os
import re
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import replace

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QColorDialog

from kanzonassvg import app, cli, engine, image, tracing
from tests.helpers import logo

RED, BLUE, WHITE = (0xB2, 0x00, 0x2D), (0x1D, 0x3F, 0x8F), (0xFF, 0xFF, 0xFF)


def fills(svg):
    return re.findall(r"fill:(#[0-9a-f]{6})", svg)


def paths(svg):
    return re.findall(r' d="([^"]*)"', svg)


def drawn(svg, w=240, h=160):
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    engine.Drawing(svg).render_image(out, 0, 0, w, h)
    return out


def rgb(c):
    return (c.red(), c.green(), c.blue())


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img = logo()
        cls.px = image.pixels(cls.img)
        cls.o = engine.Options(scans=3, smooth=False)

    def trace(self, **kw):
        return engine.trace(*self.px, options=replace(self.o, **kw))[0]

    def test_palette(self):
        pal = engine.palette(*self.px, options=self.o)
        self.assertEqual([c for c, _ in pal], [RED, BLUE, WHITE], "darkest first, as the layers")
        self.assertEqual(sum(n for _, n in pal), 240 * 160)
        self.assertEqual(engine.palette(*self.px, options=replace(self.o, mode=engine.BRIGHTNESS)), [])
        grays = engine.palette(*self.px, options=replace(self.o, mode=engine.GRAYS))
        self.assertTrue(all(c[0] == c[1] == c[2] for c, _ in grays))

    def test_recolor_keeps_the_shapes(self):
        plain = self.trace()
        green = self.trace(edits=((RED, (0, 160, 0)),))
        self.assertEqual(fills(green), ["#ffffff", "#1d3f8f", "#00a000"])
        self.assertEqual(paths(green), paths(plain), "a new color changed the shapes")
        self.assertEqual(rgb(drawn(green).pixelColor(50, 80)), (0, 160, 0))

    def test_merge(self):
        svg = self.trace(edits=((RED, BLUE),))
        self.assertEqual(fills(svg), ["#ffffff", "#1d3f8f"], "merged colors are one layer")
        out = drawn(svg)
        self.assertEqual(rgb(out.pixelColor(50, 80)), BLUE)
        self.assertEqual(rgb(out.pixelColor(165, 80)), BLUE)
        # two colors recolored the same are merged too
        svg = self.trace(edits=((RED, (9, 9, 9)), (BLUE, (9, 9, 9))))
        self.assertEqual(fills(svg), ["#ffffff", "#090909"])

    def test_leave_out(self):
        svg = self.trace(edits=((RED, None),))
        out = drawn(svg)
        self.assertEqual(out.pixelColor(50, 80).alpha(), 0, "a left-out color is see-through")
        self.assertEqual(rgb(out.pixelColor(5, 5)), WHITE)
        self.assertEqual(rgb(out.pixelColor(165, 80)), BLUE)
        # tiled too
        out = drawn(self.trace(edits=((RED, None),), stack=False))
        self.assertEqual(out.pixelColor(50, 80).alpha(), 0)

    def test_nearest_within_the_limit(self):
        near = tuple(min(255, c + 10) for c in RED)
        far = tuple(min(255, c + engine.EDIT_MATCH + 6) for c in RED)
        self.assertIn("#00a000", fills(self.trace(edits=((near, (0, 160, 0)),))))
        self.assertNotIn("#00a000", fills(self.trace(edits=((far, (0, 160, 0)),))))
        # the nearest of two edits wins
        svg = self.trace(edits=((near, (1, 1, 1)), (RED, (2, 2, 2))))
        self.assertIn("#020202", fills(svg))
        self.assertNotIn("#010101", fills(svg))
        self.assertEqual(engine.edit_for(RED, ((near, None), (RED, (2, 2, 2)))), (RED, (2, 2, 2)))

    def test_preview_grays_autotrace(self):
        o = replace(self.o, edits=((RED, (0, 160, 0)), (WHITE, None)))
        prev = engine.preview(*self.px, options=o)
        i = (80 * 240 + 50) * 3
        self.assertEqual(tuple(prev[i:i + 3]), (0, 160, 0))
        gray = engine.palette(*self.px, options=replace(self.o, mode=engine.GRAYS))[0][0]
        self.assertIn("#ff0000", fills(self.trace(mode=engine.GRAYS, edits=((gray, (255, 0, 0)),))))
        at = engine.palette(*self.px, options=replace(self.o, mode=engine.AUTOTRACE))
        red = min((c for c, _ in at), key=lambda c: sum((a - b) ** 2 for a, b in zip(c, RED)))
        svg = self.trace(mode=engine.AUTOTRACE, edits=((red, (0, 160, 0)),))
        self.assertIn("#00a000", fills(svg))
        self.assertNotIn("#b2002d", fills(svg))

    def test_a_struct_that_cuts_the_edits_pointer(self):
        # (found by the engine battery) an older caller's smaller struct whose size ends inside
        # the edits pointer: the engine took the part as a pointer and crashed; it takes no edits
        import ctypes
        lib = engine.library()
        data, w, h, stride = self.px
        buf = (ctypes.c_char * len(data)).from_buffer_copy(bytes(data))
        for size in (engine._Options.edits.offset + 1, engine._Options.edits.offset + 4,
                     engine._Options.nedits.offset + 4):
            s = replace(self.o, edits=((RED, (0, 160, 0)),))._struct()
            s.edits = ctypes.cast(16, ctypes.POINTER(engine._ColorEdit))     # (garbage)
            s.size = size
            svg, err, n = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_int()
            st = lib.kz_trace(ctypes.addressof(buf), w, h, stride, ctypes.byref(s), engine._PROGRESS(0), None,
                              ctypes.byref(svg), ctypes.byref(n), ctypes.byref(err))
            self.assertEqual(st, engine.OK)
            self.assertNotIn(b"#00a000", ctypes.string_at(svg.value))
            lib.kz_free(svg)

    def test_odd_edits(self):
        # many, duplicated, all left out: no crash, a valid SVG
        many = tuple(((k % 256, k // 256 % 256, 7), (1, 2, 3)) for k in range(5000))
        self.assertTrue(self.trace(edits=many).endswith("</svg>\n"))
        svg = self.trace(edits=((RED, None), (BLUE, None), (WHITE, None)))
        self.assertTrue(svg.endswith("</svg>\n"))
        self.assertEqual(fills(svg), [])


def wait(cond, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


class TestWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.w.a_auto_new.setChecked(False)
        self.w.settings.reset_all()
        self.w.show()
        self.w.settings.scans.setValue(3)
        self.w.settings.smooth.setChecked(False)
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())
        self.c = self.w.settings.colors

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        QApplication.processEvents()
        self.tmp.cleanup()

    def traced(self):
        w = self.w
        ok = wait(lambda: w.worker is None and not w.timer.isActive() and not w.pending and w.result is not None)
        return ok and w.job.options == w.settings.options()

    def select(self, *colors):
        for b in self.c.buttons:
            b.setChecked(False)
        for g, b in zip(self.c.groups, self.c.buttons):
            if set(g.members) & set(colors):
                b.setChecked(True)

    def test_swatches_and_merge(self):
        self.assertEqual([g.color for g in self.c.groups], [RED, BLUE, WHITE])
        self.assertFalse(self.c.b_merge.isEnabled())
        self.select(RED, BLUE)
        self.assertTrue(self.c.b_merge.isEnabled())
        self.c.b_merge.click()
        self.assertTrue(self.traced())
        # (into the color of the bigger: red, 7,000 pixels against blue's 5,404)
        self.assertEqual(fills(self.w.result.svg), ["#ffffff", "#b2002d"])
        self.assertEqual(len(self.c.groups), 2, "merged colors show as one swatch")
        # and only those are in the box (the swatches of before, deleted later, stayed on screen
        # until the event loop got to them)
        from PySide6.QtWidgets import QToolButton
        self.assertEqual(len(self.c.grid_box.findChildren(QToolButton)), 2)
        self.assertIn("1 color edited", self.w.status.text())    # (blue, now traced as red)
        # Reset colors (none selected): all back
        self.c.selected = set()
        self.c.b_reset.click()
        self.assertTrue(self.traced())
        self.assertEqual(fills(self.w.result.svg), ["#ffffff", "#1d3f8f", "#b2002d"])

    def test_change_color(self):
        self.select(RED)
        orig = QColorDialog.getColor
        QColorDialog.getColor = staticmethod(lambda *a, **k: QColor(0, 160, 0))
        try:
            self.c.b_change.click()
        finally:
            QColorDialog.getColor = orig
        self.assertTrue(self.traced())
        self.assertIn("#00a000", fills(self.w.result.svg))
        self.assertNotIn("#b2002d", fills(self.w.result.svg))
        # the picture itself is unchanged
        self.assertEqual(rgb(self.w.img.pixelColor(50, 80)), RED)

    def test_leave_out_and_put_back(self):
        self.select(RED)
        self.assertEqual(self.c.b_out.text(), "Leave out")
        self.c.b_out.click()
        self.assertTrue(self.traced())
        self.assertEqual(drawn(self.w.result.svg).pixelColor(50, 80).alpha(), 0)
        self.select(RED)
        self.assertEqual(self.c.b_out.text(), "Put back")
        self.c.b_out.click()
        self.assertTrue(self.traced())
        self.assertIn("#b2002d", fills(self.w.result.svg))
        self.assertEqual(self.c.edits, [])

    def test_click_the_picture(self):
        self.w.on_picture_clicked(QPointF(50, 80))
        self.assertEqual([g.color for g in self.c._selected_groups()], [RED])
        self.assertIn("#b2002d", self.w.status.text())
        self.w.on_picture_clicked(QPointF(5, 5))
        self.assertEqual([g.color for g in self.c._selected_groups()], [WHITE])
        self.w.on_picture_clicked(QPointF(-10, 5))             # off the picture: nothing changes
        self.assertEqual([g.color for g in self.c._selected_groups()], [WHITE])

    def test_edits_stay_with_other_settings_and_go_with_a_new_picture(self):
        self.select(RED)
        self.c.change_color((0, 160, 0))
        self.assertTrue(self.traced())
        self.w.settings.scans.setValue(6)           # the colors picked again
        self.assertTrue(self.traced())
        self.assertIn("#00a000", fills(self.w.result.svg), "the edit didn't follow the color")
        self.w.settings.mode.setCurrentIndex([m for _, m in app.MODES].index(engine.BRIGHTNESS))
        self.assertTrue(self.traced())
        self.assertFalse(self.c.isVisible())
        self.w.settings.mode.setCurrentIndex(0)
        self.assertTrue(self.traced())
        self.assertIn("#00a000", fills(self.w.result.svg))
        # an edit that matches no color now: kept, and said
        self.c.edits.append(((1, 2, 250), (0, 0, 0)))
        self.c.set_palette(self.c.palette)
        self.assertFalse(self.c.note.isHidden())
        self.w.set_image(logo(120, 80), None)
        self.assertEqual(self.c.edits, [])
        self.assertTrue(self.traced())
        self.assertIn("#b2002d", fills(self.w.result.svg))

    def test_reset_settings_clears_them(self):
        self.select(RED)
        self.c.change_color((0, 160, 0))
        self.w.settings.reset_all()
        self.assertEqual(self.c.edits, [])


class TestCommandLine(unittest.TestCase):
    def test_list_recolor_leave_out(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.png")
            logo().save(src)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.run([src, "--no-auto", "--colors", "3", "--no-smooth", "--list-colors",
                                          "--recolor", "#b2002d=#00a000"]), 0)
            text = out.getvalue()
            self.assertIn("#b2002d", text)
            self.assertIn("-> #00a000", text)
            self.assertFalse(os.path.exists(os.path.join(d, "a.svg")), "--list-colors wrote an SVG")
            self.assertEqual(cli.run([src, "-q", "--no-auto", "--colors", "3", "--no-smooth",
                                      "--recolor", "#b2002d=#00a000", "--leave-out", "#ffffff"]), 0)
            with open(os.path.join(d, "a.svg"), encoding="utf-8") as f:
                svg = f.read()
            self.assertEqual(fills(svg), ["#1d3f8f", "#00a000"])
            with self.assertRaises(SystemExit):
                cli.run([src, "--recolor", "red=blue"])
            with self.assertRaises(SystemExit):
                cli.run([src, "--leave-out", "#12345"])


if __name__ == "__main__":
    unittest.main()
