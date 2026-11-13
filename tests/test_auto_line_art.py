"""Auto settings on line art (a plan, a drawing, a screenshot of one: thin lines on a plain
background), and Auto setting every setting. Before 1.1.1 a drawing of thin gray lines lost
them: Auto counted colors on flat areas only (lines have none), smoothed their soft edges away,
and the gray of a one-pixel line was taken for an edge shade between white and a dark area
elsewhere and dropped."""

import re
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, engine, image, tracing
from tests.helpers import logo

GRAY = QColor(0x9A, 0x9A, 0x9A)
BLUE = QColor(0x1F, 0x3C, 0xC8)


def plan(w=900, h=560, dark_strip=False):
    """A floor plan as drawn by a CAD program: one-pixel gray outlines (chairs, a table, a door),
    blue labels with leader lines; optionally a dark toolbar strip (as in a screenshot)."""
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(Qt.GlobalColor.white)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(GRAY, 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(100.5, 220.5, 620, 110))                     # the table
    for k in range(8):                                              # chairs on both sides
        for y in (160, 345):
            p.drawRoundedRect(QRectF(115 + 75 * k, y, 55, 50), 12, 12)
    p.drawArc(QRectF(20, -80, 160, 160), 270 * 16, 90 * 16)        # a door
    p.drawLine(QPointF(100, 0), QPointF(100, 80))
    p.setPen(QPen(BLUE, 1.5))
    for x, y, text in ((330, 120, "PRESENTER CAMERA"), (560, 260, "CONTROL PANEL"), (760, 420, "MOBILE LECTERN")):
        p.drawLine(QPointF(x - 40, y + 30), QPointF(x - 5, y - 4))
        p.drawLine(QPointF(x - 5, y - 4), QPointF(x, y - 4))
    p.setFont(QFont("DejaVu Sans", 11, QFont.Weight.Bold))
    for x, y, text in ((330, 120, "PRESENTER CAMERA"), (560, 260, "CONTROL PANEL"), (760, 420, "MOBILE LECTERN")):
        p.drawText(QPointF(x, y), text)
    if dark_strip:
        p.fillRect(QRectF(0, h - 30, w, 30), QColor(0x2F, 0x2F, 0x2F))
    p.end()
    return image.to_rgba(img)


def keep_for_looking(img, svg, name):
    """A failed test's picture and SVG, in build/test-failures/ (the build uploads them)."""
    import os
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "test-failures")
    os.makedirs(folder, exist_ok=True)
    img.save(os.path.join(folder, name + ".png"))
    with open(os.path.join(folder, name + ".svg"), "w", encoding="utf-8") as f:
        f.write(svg)


def drawn(img, svg):
    out = QImage(img.width(), img.height(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.white)
    engine.Drawing(svg).render_image(out, 0, 0, img.width(), img.height())
    return out


def line_kept(out, points):
    """How many of points the traced SVG drew clearly not white."""
    return sum(1 for x, y in points if min(out.pixelColor(x, y).red(), out.pixelColor(x, y).green()) < 215)


# points on the one-pixel gray lines (the table's top edge, a chair's side)
ON_LINES = [(150 + 40 * k, 220) for k in range(14)] + [(115, 175 + 5 * k) for k in range(6)]


class TestLineArt(unittest.TestCase):
    def test_a_plan_is_line_art(self):
        img = plan()
        o, info = engine.auto(*image.pixels(img))
        self.assertTrue(info.line_art)
        self.assertFalse(o.smooth, "smoothing wipes thin lines out")
        self.assertEqual(info.enlarge, 4)
        res = tracing.trace_image(img, o, info.enlarge)
        fills = re.findall(r"fill:#([0-9a-f]{6})", res.svg)
        self.assertTrue(any(abs(int(f[0:2], 16) - int(f[2:4], 16)) < 12 and 0x70 < int(f[0:2], 16) < 0xe0
                            for f in fills), "no gray for the lines: %s" % fills)
        kept = line_kept(drawn(img, res.svg), ON_LINES)
        if kept < len(ON_LINES) * 0.9:
            keep_for_looking(img, res.svg, "plan")
        self.assertGreaterEqual(kept, len(ON_LINES) * 0.9, "the gray lines are gone (%d of %d); Auto: %d colors, "
                                "%s, fills %s" % (kept, len(ON_LINES), o.scans, info, fills))

    def test_gray_lines_are_not_edge_shades(self):
        # with a dark strip elsewhere, gray lies between white and it, but the lines touch only
        # white: they're lines of their own color, not the soft edge of the strip
        img = plan(dark_strip=True)
        res = tracing.trace_image(img, engine.Options(scans=6, smooth=False), 4)
        kept = line_kept(drawn(img, res.svg), ON_LINES)
        if kept < len(ON_LINES) * 0.9:
            keep_for_looking(img, res.svg, "plan-dark-strip")
        self.assertGreaterEqual(kept, len(ON_LINES) * 0.9, "gray lines dropped (%d of %d)" % (kept, len(ON_LINES)))

    def test_logos_and_photos_are_not_line_art(self):
        for img in (logo(), logo(900, 600)):
            _o, info = engine.auto(*image.pixels(img))
            self.assertFalse(info.line_art)
            self.assertEqual(info.enlarge, 0)


class TestAutoSetsEverything(unittest.TestCase):
    def test_auto_resets_the_curve_settings(self):
        w = app.MainWindow()
        try:
            s = w.settings
            s.speckles.setValue(8)
            s.corners.setValue(0.0)
            s.optimize.setChecked(False)
            s.tolerance.setValue(0.0)
            s.enlarge.setCurrentIndex(s.enlarge.findData(1))
            w.set_image(plan(), None)
            end = __import__("time").time() + 60
            while (w.worker is not None or w.result is None) and __import__("time").time() < end:
                QApplication.processEvents()
            self.assertIsNotNone(w.result)
            self.assertEqual((s.speckles.value(), s.corners.value(), s.optimize.isChecked(), s.tolerance.value()),
                             (2, 1.0, True, 0.2))
            self.assertEqual(s.enlarge_setting(), 4, "line art: Enlarge first 4 times")
            self.assertEqual(w.result.factor, 4)
            self.assertIn("thin lines", w.status.text())
            # and what's shown is what was traced
            self.assertEqual(w.job.options, s.options())
        finally:
            w.a_auto_new.setChecked(True)
            w.settings.reset_all()
            w.close()


if __name__ == "__main__":
    unittest.main()
