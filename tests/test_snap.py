"""Snap shapes (kz_options.snap, core/src/snap.h): straight edges straight, level and upright
ones exactly so, round shapes perfect circles and ellipses; off by default and in Autotrace;
the window's checkbox (Auto leaves it), the command line, an older caller's struct."""

import io
import os
import re
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from dataclasses import replace

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, cli, engine, image
from tests.helpers import canvas, logo

O = engine.Options(scans=2, smooth=False, remove_background=engine.BG_REMOVE)


def draw(fn, w=400, h=300):
    img = canvas(w, h)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0x1D, 0x3F, 0x8F))
    fn(p)
    p.end()
    return image.to_rgba(img)


def trace(img, snap, **kw):
    return engine.trace(*image.pixels(img), options=replace(O, snap=snap, **kw))[0]


def pieces(svg, color=None):
    """[(command, [numbers])] of the SVG's paths (of one color: "#rrggbb"), in order."""
    out = []
    for style, d in re.findall(r'<path style="([^"]*)" d="([^"]*)"', svg):
        if color and color not in style:
            continue
        for c, a in re.findall(r"([MLCZ])([^MLCZ]*)", d):
            out.append((c, [float(v) for v in a.replace(",", " ").split()]))
    return out


def lines(svg):
    """The straight lines: [((x0, y0), (x1, y1))]."""
    out, cur, start = [], None, None
    for c, n in pieces(svg):
        if c == "M":
            cur = start = tuple(n[-2:])
        elif c == "L":
            out.append((cur, tuple(n[-2:])))
            cur = tuple(n[-2:])
        elif c == "C":
            cur = tuple(n[-2:])
        else:
            cur = start
    return out


def drawn(svg, w, h):
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.white)
    engine.Drawing(svg).render_image(out, 0, 0, w, h)
    return out


def differ(a, b):
    n = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            if max(abs(ca.red() - cb.red()), abs(ca.green() - cb.green()), abs(ca.blue() - cb.blue())) > 64:
                n += 1
    return n / ((a.width() // 2) * (a.height() // 2))


class TestEngine(unittest.TestCase):
    def test_a_slightly_turned_box_comes_out_square(self):
        def box(p):
            p.translate(200, 150)
            p.rotate(0.6)
            p.drawRect(QRectF(-150, -100, 300, 200))
        img = draw(box)
        before, after = lines(trace(img, 0)), lines(trace(img, engine.SNAP_ALL))
        square = [ln for ln in after if ln[0][0] == ln[1][0] or ln[0][1] == ln[1][1]]
        self.assertEqual(len(after), 4, after)
        self.assertEqual(len(square), 4, after)
        self.assertLess(sum(1 for ln in before if ln[0][0] == ln[1][0] or ln[0][1] == ln[1][1]), 4)
        # the box squared: its corners moved up to 300 x tan(0.6 degrees) / 2 = 1.6 pixels, no more
        self.assertLess(differ(drawn(trace(img, engine.SNAP_ALL), 400, 300), img), 0.015)
        self.assertLess(differ(drawn(trace(img, 0), 400, 300), img), 0.004)

    def test_a_circle_becomes_four_exact_arcs(self):
        img = draw(lambda p: p.drawEllipse(QPointF(200, 150), 90, 90))
        svg = trace(img, engine.SNAP_ALL)
        ps = pieces(svg)
        self.assertEqual([c for c, _ in ps], ["M", "C", "C", "C", "C", "Z"], ps)
        x0, y0 = ps[0][1]
        r = x0 - 200
        self.assertAlmostEqual(y0, 150, delta=0.3)
        self.assertAlmostEqual(r, 90, delta=0.3)
        c1 = ps[1][1]
        # first arc: from the right a quarter round, to the top or bottom (y down: either way
        # round), its handles 0.5523 of the radius long (the radius as this arc has it: the
        # numbers are rounded to 3 decimals)
        end_x, end_y = c1[4], c1[5]
        radius = abs(end_y - y0)
        self.assertAlmostEqual(c1[0], x0, delta=0.002)
        self.assertAlmostEqual(abs(c1[1] - y0) / radius, 0.5522847498, delta=0.0002)
        self.assertAlmostEqual(abs(c1[2] - end_x) / radius, 0.5522847498, delta=0.0002)
        self.assertGreater(len(pieces(trace(img, 0))), 6)

    def test_an_ellipse_and_a_ring(self):
        def ring(p):
            path = QPainterPath()
            path.addEllipse(QPointF(200, 150), 160, 80)
            path.addEllipse(QPointF(200, 150), 60, 60)
            p.drawPath(path)                        # (odd-even: the inner one is a hole)
        img = draw(ring)
        svg = trace(img, engine.SNAP_ALL)
        ps = pieces(svg, "#1d3f8f")         # (the blue ring: the outer ellipse and its hole)
        self.assertEqual("".join(c for c, _ in ps), "MCCCCZMCCCCZ", ps)
        xs = [n[-2] for c, n in ps if c in "MC"]
        self.assertAlmostEqual(max(xs) - min(xs), 320, delta=0.6)
        # the hole is still a hole
        d = drawn(svg, 400, 300)
        self.assertEqual(d.pixelColor(200, 150).name(), "#ffffff")
        self.assertEqual(d.pixelColor(100, 150).name(), "#1d3f8f")
        self.assertLess(differ(d, drawn(trace(img, 0), 400, 300)), 0.004)

    def test_shapes_that_arent_ellipses_stay(self):
        def shapes(p):
            p.drawRoundedRect(QRectF(20, 20, 160, 160), 40, 40)
            p.drawPolygon([QPointF(220, 250), QPointF(380, 250), QPointF(300, 60)])
        img = draw(shapes)
        ps = pieces(trace(img, engine.SNAP_ALL))
        # the rounded square: its four sides straight lines, level and upright
        square = [ln for ln in lines(trace(img, engine.SNAP_ALL))
                  if ln[0][0] < 200 and (ln[0][0] == ln[1][0] or ln[0][1] == ln[1][1])]
        self.assertGreaterEqual(len(square), 4)
        self.assertGreater(len(ps), 12)
        d = drawn(trace(img, engine.SNAP_ALL), 400, 300)
        self.assertLess(differ(d, drawn(trace(img, 0), 400, 300)), 0.004)

    def test_off_by_default_and_not_in_autotrace(self):
        img = logo()
        self.assertEqual(engine.Options().snap, 0)
        self.assertEqual(trace(img, 0), engine.trace(*image.pixels(img), options=replace(O))[0])
        a = trace(img, 0, mode=engine.AUTOTRACE)
        self.assertEqual(a, trace(img, engine.SNAP_ALL, mode=engine.AUTOTRACE))
        self.assertNotEqual(trace(img, 0), trace(img, engine.SNAP_ALL))

    def test_an_older_callers_struct(self):
        # a caller built before snap (its struct ends at the edits): snap stays off
        img = logo()
        whole = engine.Options._struct

        def older(self):
            st = whole(self)
            st.size = engine._Options.snap.offset
            return st
        engine.Options._struct = older
        try:
            svg = engine.trace(*image.pixels(img), options=replace(O, snap=engine.SNAP_ALL))[0]
        finally:
            engine.Options._struct = whole
        self.assertEqual(svg, trace(img, 0))

    def test_every_number_of_pieces_is_safe(self):
        # tiny and odd shapes: dots, slivers, a one-pixel line, stairs
        def odd(p):
            p.drawRect(QRectF(10, 10, 1, 1))
            p.drawRect(QRectF(30, 10, 2, 40))
            p.drawRect(QRectF(50, 10, 100, 1))
            for k in range(10):
                p.drawRect(QRectF(200 + 8 * k, 20 + 6 * k, 8, 6))
            p.drawEllipse(QPointF(100, 200), 3, 3)
            p.drawEllipse(QPointF(300, 200), 60, 2)
        img = draw(odd)
        svg = trace(img, engine.SNAP_ALL)
        self.assertLess(differ(drawn(svg, 400, 300), drawn(trace(img, 0), 400, 300)), 0.006)


class TestWindowAndCli(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.w.show()
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())

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

    def test_the_checkbox(self):
        s = self.w.settings
        self.assertFalse(s.snap.isChecked())
        before = self.w.result.svg
        s.snap.setChecked(True)
        self.assertTrue(self.traced())
        self.assertEqual(self.w.job.options.snap, engine.SNAP_ALL)
        self.assertNotEqual(self.w.result.svg, before)
        # Auto leaves it as it is
        s.auto.click()
        self.assertTrue(self.traced())
        self.assertTrue(s.snap.isChecked())
        self.assertEqual(self.w.job.options.snap, engine.SNAP_ALL)
        # Undo takes it back; Reset settings turns it off
        self.w.undo()
        self.w.undo()
        self.assertTrue(self.traced())
        self.assertFalse(s.snap.isChecked())
        self.w.redo()
        self.assertTrue(self.traced())
        self.assertTrue(s.snap.isChecked())
        s.reset_all()
        self.assertTrue(self.traced())
        self.assertFalse(s.snap.isChecked())
        # Curves (and the checkbox) only in Potrace's modes
        s.mode.setCurrentIndex([m for _, m in app.MODES].index(engine.AUTOTRACE))
        self.assertFalse(s.g_potrace.isVisible())

    def test_command_line(self):
        png = os.path.join(self.tmp.name, "a.png")
        logo().save(png)
        outs = []
        for flag in ([], ["--snap"]):
            out = os.path.join(self.tmp.name, "a%d.svg" % len(flag))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.run([png, "-o", out, "-q"] + flag), 0)
            with open(out, encoding="utf-8") as f:
                outs.append(f.read())
        self.assertNotEqual(outs[0], outs[1])
        self.assertLess(outs[1].count("C"), outs[0].count("C"))


if __name__ == "__main__":
    unittest.main()
