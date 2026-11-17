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

from kanzonassvg import app, cli, engine, image
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
        # darkest first, as the layers; then the background (white around the logo) on its own,
        # apart from the white inside the ring
        self.assertEqual([(c, bg) for c, _n, bg in pal], [(RED, False), (BLUE, False), (WHITE, False), (WHITE, True)])
        self.assertEqual(sum(n for _c, n, _bg in pal), 240 * 160)
        self.assertGreater(pal[2][1], 0, "no white inside the ring")
        pal, mask = engine.palette(*self.px, options=self.o, mask=True)
        self.assertEqual(len(mask), 240 * 160)
        self.assertEqual(mask[5 * 240 + 5], 1, "the corner is background")
        self.assertEqual(mask[55 * 240 + 165], 0, "inside the ring isn't")
        self.assertEqual(mask.count(1), pal[3][1])
        self.assertEqual(engine.palette(*self.px, options=replace(self.o, mode=engine.BRIGHTNESS)), [])
        grays = engine.palette(*self.px, options=replace(self.o, mode=engine.GRAYS))
        self.assertTrue(all(c[0] == c[1] == c[2] for c, _n, _bg in grays))

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
        red = min((c for c, _n, _bg in at), key=lambda c: sum((a - b) ** 2 for a, b in zip(c, RED)))
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

    def test_the_background_apart_from_that_color_inside(self):
        # (asked for: merging the white inside the picture merged the whole background with it)
        inside = drawn(self.trace(edits=((WHITE, (0, 160, 0), engine.INSIDE),)))
        self.assertEqual(rgb(inside.pixelColor(165, 55)), (0, 160, 0), "the white inside the ring")
        self.assertEqual(rgb(inside.pixelColor(5, 5)), WHITE, "the background changed with it")
        back = drawn(self.trace(edits=((WHITE, (250, 230, 0), engine.BACKGROUND),)))
        self.assertEqual(rgb(back.pixelColor(5, 5)), (250, 230, 0))
        self.assertEqual(rgb(back.pixelColor(165, 55)), WHITE, "the inside changed with the background")
        both = drawn(self.trace(edits=((WHITE, (9, 9, 9)),)))      # (everywhere: the command line's)
        self.assertEqual((rgb(both.pixelColor(5, 5)), rgb(both.pixelColor(165, 55))), ((9, 9, 9), (9, 9, 9)))
        # an edit for the area over one for everywhere
        svg = self.trace(edits=((WHITE, (9, 9, 9)), (WHITE, (250, 230, 0), engine.BACKGROUND)))
        out = drawn(svg)
        self.assertEqual((rgb(out.pixelColor(5, 5)), rgb(out.pixelColor(165, 55))), ((250, 230, 0), (9, 9, 9)))
        # Background: Remove takes the picture's background, whatever it's traced as
        out = drawn(self.trace(remove_background=engine.BG_REMOVE, edits=((WHITE, (250, 230, 0), engine.BACKGROUND),)))
        self.assertEqual(out.pixelColor(5, 5).alpha(), 0)
        self.assertEqual(rgb(out.pixelColor(165, 55)), WHITE)
        # and merging another color into white keeps it a shape (not the background, which goes)
        out = drawn(self.trace(remove_background=engine.BG_REMOVE, edits=((RED, WHITE),)))
        self.assertEqual(out.pixelColor(50, 80).alpha(), 255)
        self.assertEqual(rgb(out.pixelColor(50, 80)), WHITE)
        self.assertEqual(out.pixelColor(5, 5).alpha(), 0)
        # no edits: the same SVG as before there was a background swatch (one white layer)
        self.assertEqual(fills(self.trace()), ["#ffffff", "#1d3f8f", "#b2002d"])

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

    def select(self, *colors, background=False):
        """A click on the first color's swatch, Ctrl+clicks on the others' (the swatches of the
        areas inside the picture, or with background=True the background's)."""
        first = True
        for g in list(self.c.groups):
            if g.background == background and {m for m, _w in g.members} & set(colors):
                self.c.click_group(g, add=not first)
                first = False

    def merge_into(self, color):
        """Merge, picking <color> from the list it opens."""
        self.c.open_menu = lambda menu, where: next(x for x in menu.actions() if x.text().startswith(
            "#%02x%02x%02x" % color))
        try:
            self.c.b_merge.click()
        finally:
            del self.c.open_menu

    def test_swatches_and_merge(self):
        self.assertEqual([(g.color, g.background) for g in self.c.groups],
                         [(RED, False), (BLUE, False), (WHITE, False), (WHITE, True)])
        self.assertFalse(self.c.b_merge.isEnabled())
        self.select(RED, BLUE)
        self.assertTrue(self.c.b_merge.isEnabled())
        self.merge_into(BLUE)                       # (the one picked: blue, the smaller of the two)
        self.assertTrue(self.traced())
        self.assertEqual(fills(self.w.result.svg), ["#ffffff", "#1d3f8f"])
        self.assertEqual(len(self.c.groups), 3, "merged colors show as one swatch")
        # and only those are in the box (the swatches of before, deleted later, stayed on screen
        # until the event loop got to them)
        from PySide6.QtWidgets import QToolButton
        self.assertEqual(len(self.c.grid_box.findChildren(QToolButton)), 3)
        self.assertIn("1 color edited", self.w.status.text())    # (red, now traced as blue)
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

    def test_merging_the_white_inside_leaves_the_background(self):
        # (asked for) the white inside the ring merged with blue: the background stays white
        self.select(WHITE, BLUE)
        self.merge_into(BLUE)
        self.assertTrue(self.traced())
        out = drawn(self.w.result.svg)
        self.assertEqual(rgb(out.pixelColor(165, 55)), BLUE)
        self.assertEqual(rgb(out.pixelColor(5, 5)), WHITE)
        # clicks: the background selects the background's swatch, inside the ring the other
        self.w.on_picture_clicked(QPointF(5, 5))
        self.assertEqual([g.background for g in self.c._selected_groups()], [True])
        self.assertIn("the background", self.w.status.text())
        self.w.on_picture_clicked(QPointF(165, 55))
        self.assertEqual([(g.background, g.color) for g in self.c._selected_groups()], [(False, BLUE)])
        # the background on its own: changed, then left out, then put back
        self.select(WHITE, background=True)
        self.c.change_color((250, 230, 0))
        self.assertTrue(self.traced())
        out = drawn(self.w.result.svg)
        self.assertEqual((rgb(out.pixelColor(5, 5)), rgb(out.pixelColor(165, 55))), ((250, 230, 0), BLUE))
        self.select(WHITE, background=True)
        self.c.leave_out()
        self.assertTrue(self.traced())
        self.assertEqual(drawn(self.w.result.svg).pixelColor(5, 5).alpha(), 0)
        self.c.leave_out()                          # (still selected: Put back, in its own color)
        self.assertTrue(self.traced())
        self.assertEqual(rgb(drawn(self.w.result.svg).pixelColor(5, 5)), WHITE)
        self.assertEqual(rgb(drawn(self.w.result.svg).pixelColor(165, 55)), BLUE)

    def test_a_few_stray_pixels_go_with_the_background(self):
        # the background color's only pixels inside are a 2 x 2 spot in a shape: no swatch of
        # their own (a second sky swatch for 4 pixels), and the background's edits take them too
        img = QImage(400, 300, QImage.Format.Format_RGBA8888)
        img.fill(QColor(*WHITE))
        for y in range(80, 220):
            for x in range(100, 300):
                img.setPixelColor(x, y, QColor(*RED))
        for y in (150, 151):
            for x in (200, 201):
                img.setPixelColor(x, y, QColor(*WHITE))
        img = image.to_rgba(img)
        self.w.settings.speckles.setValue(0)
        self.w.set_image(img, None)
        self.assertTrue(self.traced())
        self.assertEqual([(g.color, g.background) for g in self.c.groups], [(RED, False), (WHITE, True)])
        self.c.click_group(self.c.groups[1])
        self.c.change_color((0, 0, 200))
        self.assertTrue(self.traced())
        self.assertNotIn("#ffffff", fills(self.w.result.svg), "the stray white stayed white")

    def test_ctrl_click_on_the_svg(self):
        # a click selects just that color; Ctrl+click adds one, or takes a selected one out
        right = self.w.right
        self.w.on_picture_clicked(QPointF(50, 80))                 # red (as the SVG's click gives it)
        self.w.on_picture_clicked(QPointF(165, 30), add=True)      # + blue
        self.assertEqual(sorted(g.color for g in self.c._selected_groups()), sorted([RED, BLUE]))
        self.assertIn("2 colors selected", self.w.status.text())
        self.w.on_picture_clicked(QPointF(165, 30), add=True)      # blue out again
        self.assertEqual([g.color for g in self.c._selected_groups()], [RED])
        self.w.on_picture_clicked(QPointF(5, 5))                   # just white
        self.assertEqual([g.color for g in self.c._selected_groups()], [WHITE])
        # the SVG side sends its clicks with Ctrl's state
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent
        t = self.w.view.target(right.size())
        s = self.w.view.scale
        for x, y, mod in ((50, 80, Qt.KeyboardModifier.NoModifier), (165, 30, Qt.KeyboardModifier.ControlModifier)):
            pos = QPointF(t.x() + x * s, t.y() + y * s)
            for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                buttons = Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton
                QApplication.sendEvent(right, QMouseEvent(kind, pos, right.mapToGlobal(pos), Qt.MouseButton.LeftButton,
                                                          buttons, mod))
        self.assertEqual(sorted(g.color for g in self.c._selected_groups()), sorted([RED, BLUE]))
        # swatches the same way
        self.c.click_group(self.c.groups[2])
        self.assertEqual([g.color for g in self.c._selected_groups()], [WHITE])

    def test_merge_into_another_color(self):
        self.select(RED, BLUE)
        self.c.open_menu = lambda menu, where: next(x for x in menu.actions() if x.data() == "other")
        orig = QColorDialog.getColor
        QColorDialog.getColor = staticmethod(lambda *a, **k: QColor(9, 9, 9))
        try:
            self.c.b_merge.click()
        finally:
            QColorDialog.getColor = orig
            del self.c.open_menu
        self.assertTrue(self.traced())
        self.assertEqual(fills(self.w.result.svg), ["#ffffff", "#090909"])
        # the list chosen from: nothing chosen, nothing merged
        self.select(WHITE, (9, 9, 9))
        self.c.open_menu = lambda menu, where: None
        self.c.b_merge.click()
        del self.c.open_menu
        self.assertEqual(fills(self.w.result.svg), ["#ffffff", "#090909"])

    def test_undo_and_redo(self):
        w = self.w
        self.assertFalse(w.a_undo.isEnabled())
        first = w.result.svg
        self.select(RED)
        self.c.change_color((0, 160, 0))
        self.assertTrue(self.traced())
        green = w.result.svg
        w.settings.speckles.setValue(9)
        self.assertTrue(self.traced())
        w.crop_to(app.QRect(0, 0, 120, 160))
        self.assertTrue(self.traced())
        self.assertTrue(w.a_undo.isEnabled())
        w.a_undo.trigger()                                 # the crop goes
        self.assertTrue(self.traced())
        self.assertIsNone(w.crop)
        self.assertEqual(w.settings.speckles.value(), 9)
        w.a_undo.trigger()                                 # speckles back
        self.assertTrue(self.traced())
        self.assertEqual(w.settings.speckles.value(), 2)
        self.assertEqual(w.result.svg, green)
        w.a_undo.trigger()                                 # the color edit goes
        self.assertTrue(self.traced())
        self.assertEqual(w.result.svg, first)
        self.assertEqual(self.c.edits, [])
        self.assertFalse(w.a_undo.isEnabled())
        w.a_redo.trigger()
        self.assertTrue(self.traced())
        self.assertEqual(w.result.svg, green)
        self.assertTrue(w.a_redo.isEnabled())
        # a change after an Undo: no Redo
        w.settings.speckles.setValue(4)
        self.assertTrue(self.traced())
        self.assertFalse(w.a_redo.isEnabled())
        # a new picture starts afresh
        w.set_image(logo(120, 80), None)
        self.assertTrue(self.traced())
        self.assertFalse(w.a_undo.isEnabled())

    def test_the_svg_size_shown(self):
        size = len(self.w.result.svg.encode("utf-8"))
        self.assertEqual(self.w.right.title, "SVG: %s, %d shapes" % (app._size_text(size), self.w.result.shapes))
        path = os.path.join(self.tmp.name, "out.svg")
        self.assertTrue(self.w.write(path))
        self.assertEqual(os.path.getsize(path), size, "the size shown isn't the size saved")

    def test_the_colors_arrows_stay_under_the_mouse(self):
        # (the owner: changing the number of colors moved the panel, and the mouse was no longer
        # over the arrows) more colors brought the scroll bar (the panel 14 px narrower: the
        # arrows moved sideways); fewer, scrolled to the bottom, pulled it all 42 px down
        from PySide6.QtCore import QPoint
        here = os.path.dirname(os.path.abspath(__file__))
        self.w.set_image(image.load(os.path.join(here, "reference", "starry-night.jpg")), None)
        self.assertTrue(self.traced())
        sp = self.w.settings.scans
        for height in (900, 600):
            self.w.resize(1400, height)
            QApplication.processEvents()
            if height == 600:
                bar = self.w.settings.verticalScrollBar()
                bar.setValue(bar.maximum())
                QApplication.processEvents()
            spots = set()
            for n in (8, 24, 40, 6, 30, 3):
                sp.setValue(n)
                self.assertTrue(self.traced())
                QApplication.processEvents()
                spots.add(sp.mapTo(self.w, QPoint(sp.width() - 8, 6)).toTuple())
            self.assertEqual(len(spots), 1, "the arrows moved (window %d px tall): %s" % (height, sorted(spots)))
        # a new picture: the box compact again
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())
        self.assertLess(self.c.grid_box.minimumHeight(), 100)

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
