"""Saving as SVG, PDF, EPS and DXF at a size (1.3): each file drawn or read back and compared
with the SVG the engine drew (PDF with PyMuPDF, EPS with Ghostscript, DXF read with ezdxf and
drawn with Qt); the color groups; Saved width; the node count; the window and the command line."""

import io
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tests import helpers  # noqa: F401 (Qt first)
import numpy as np
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, cli, engine, export, image, tracing
from tests.helpers import logo

HERE = os.path.dirname(os.path.abspath(__file__))


def reference(name):
    return image.load(os.path.join(HERE, "reference", name))


def array(img):
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
    return a[:, :img.width() * 3].reshape(img.height(), img.width(), 3).astype(int)


def drawn(svg, w, h):
    """The SVG drawn by the engine (as the window shows it), on white."""
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.white)
    engine.Drawing(svg).render_image(out, 0, 0, w, h)
    return array(out)


def off(a, b):
    """The share of pixels clearly a different color (over a quarter of the way off)."""
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    return float((np.abs(a[:h, :w] - b[:h, :w]).max(axis=2) > 64).mean())


TRACES = {}


def traced(name, mode=None):
    """(svg, width, height) of a reference picture traced as the window would (Auto settings)."""
    key = (name, mode)
    if key not in TRACES:
        img = reference(name)
        o, info = engine.auto(*image.pixels(img))
        if mode is not None:
            o.mode = mode
        res = tracing.trace_image(img, o, info.enlarge or tracing.AUTO)
        TRACES[key] = (res.svg, img.width(), img.height())
    return TRACES[key]


CASES = [("logo.png", None), ("smiley.png", None), ("plan.png", None), ("starry-night.jpg", engine.AUTOTRACE),
         ("logo.png", engine.CENTERLINE)]


class TestSvg(unittest.TestCase):
    def test_one_group_for_each_color(self):
        svg = traced("smiley.png")[0]
        groups = re.findall(r'<g id="color-([0-9a-f]{6})" inkscape:groupmode="layer" inkscape:label="#([0-9a-f]{6})">',
                            svg)
        self.assertGreater(len(groups), 2)
        self.assertEqual(svg.count("<g "), len(groups))
        self.assertEqual(svg.count("<g "), svg.count("</g>"))
        for gid, label in groups:
            self.assertEqual(gid, label)
        # each color's paths are in its group, and each group's paths are its color
        for m in re.finditer(r'<g id="color-([0-9a-f]{6})"[^>]*>(.*?)</g>', svg, re.S):
            colors = set(re.findall(r"(?:fill|stroke):#([0-9a-f]{6})", m.group(2)))
            self.assertEqual(colors, {m.group(1)})
        # in the layered modes, a color is one group
        self.assertEqual(len({g for g, _ in groups}), len(groups))

    def test_colors_coming_back_get_groups_of_their_own(self):
        svg = traced("starry-night.jpg", engine.AUTOTRACE)[0]
        ids = re.findall(r'<g id="([^"]+)"', svg)
        self.assertEqual(len(ids), len(set(ids)), "ids repeated")
        self.assertTrue(any(re.search(r"-\d+$", i) for i in ids), "no color came back (the test needs one)")
        # the shapes are in the same order as before groups (the drawing is unchanged)
        self.assertEqual(re.findall(r'<path style="([^"]*)"', svg),
                         [s for s, _ in re.findall(r'<path style="([^"]*)" d="([^"]*)"', svg)])

    def test_the_svg_reads_in_qt_and_says_the_version(self):
        from kanzonassvg import __version__
        svg, w, h = traced("logo.png")
        self.assertIn("<!-- Created with KanzonasSVG %s -->" % __version__, svg)
        a = array(helpers.render(svg, w, h).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        self.assertLess(off(a, drawn(svg, w, h)), 0.002)


class TestSize(unittest.TestCase):
    def setUp(self):
        self.svg, self.w, self.h = traced("logo.png")          # 1200 x 500

    def test_pixels_are_96_to_the_inch(self):
        self.assertEqual(export.inches(self.svg), (12.5, 500 / 96))
        self.assertEqual(export.sized_svg(self.svg), self.svg)
        self.assertEqual(export.size_text(self.svg), "1200 x 500 pixels (12.5 x 5.21 in)")

    def test_inches_and_millimeters(self):
        s = export.sized_svg(self.svg, export.Size(export.IN, 4))
        self.assertIn('width="4in" height="1.6667in" viewBox="0 0 %d %d"' % export.svg_size(self.svg)[2:], s)
        s = export.sized_svg(self.svg, export.Size(export.MM, 100))
        self.assertIn('width="100mm" height="41.6667mm"', s)
        self.assertEqual(export.size_text(self.svg, export.Size(export.MM, 100)), "100 x 41.67 mm")
        self.assertEqual(export.svg_size(s)[:2], (100.0, 41.6667))
        for bad in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                export.Size(export.IN, bad)
        with self.assertRaises(ValueError):
            export.Size("ft", 1)


class TestPdfEps(unittest.TestCase):
    def test_pdf_matches_the_svg(self):
        import pymupdf
        for name, mode in CASES:
            svg, w, h = traced(name, mode)
            pdf = export.to_pdf(svg)
            doc = pymupdf.open(stream=pdf, filetype="pdf")
            self.assertEqual(len(doc), 1)
            page = doc[0]
            self.assertAlmostEqual(page.rect.width, w * 72 / 96, places=2)
            self.assertAlmostEqual(page.rect.height, h * 72 / 96, places=2)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(96 / 72, 96 / 72), alpha=False)
            got = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
            share = off(got, drawn(svg, w, h))
            self.assertLess(share, 0.004, "%s: %.2f%% of the PDF is off" % (name, 100 * share))

    def test_pdf_at_a_size(self):
        import pymupdf
        svg = traced("logo.png")[0]
        page = pymupdf.open(stream=export.to_pdf(svg, export.Size(export.MM, 100)), filetype="pdf")[0]
        self.assertAlmostEqual(page.rect.width / 72 * 25.4, 100, places=2)
        self.assertAlmostEqual(page.rect.height / 72 * 25.4, 100 * 500 / 1200, places=2)

    def test_eps(self):
        svg, w, h = traced("smiley.png")
        eps = export.to_eps(svg).decode("ascii")
        self.assertTrue(eps.startswith("%!PS-Adobe-3.0 EPSF-3.0\n"))
        self.assertIn("%%%%BoundingBox: 0 0 %d %d" % (math.ceil(w * 0.75), math.ceil(h * 0.75)), eps)
        self.assertLessEqual(max(len(line) for line in eps.splitlines()), 255)   # (PostScript's line limit)
        self.assertEqual(eps.count(" setrgbcolor"), len(export.shapes(svg)))
        gs = shutil.which("gs") or shutil.which("gswin64c")
        if not gs:
            self.skipTest("Ghostscript isn't installed here (the Linux build installs it)")
        for name, mode in CASES:
            svg, w, h = traced(name, mode)
            with tempfile.TemporaryDirectory() as d:
                src, png = os.path.join(d, "x.eps"), os.path.join(d, "x.png")
                with open(src, "wb") as f:
                    f.write(export.to_eps(svg))
                subprocess.run([gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dEPSCrop", "-sDEVICE=png16m", "-r96",
                                "-dGraphicsAlphaBits=4", "-sOutputFile=" + png, src], check=True)
                share = off(array(QImage(png)), drawn(svg, w, h))
            self.assertLess(share, 0.006, "%s: %.2f%% of the EPS is off" % (name, 100 * share))


def dxf_drawn(path, w, h):
    """The DXF's polylines filled with Qt (a run of one layer's polylines as one path, as the
    SVG's paths of a color), bottom up, at w x h pixels; open polylines as lines."""
    import ezdxf
    doc = ezdxf.readfile(path)
    ext_w = doc.header["$EXTMAX"][0]
    k = w / ext_w
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.white)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    runs = []
    for e in doc.modelspace():
        if runs and runs[-1][0] == e.dxf.layer:
            runs[-1][1].append(e)
        else:
            runs.append((e.dxf.layer, [e]))
    for layer, ents in runs:
        color = QColor("#" + layer[len("COLOR_"):])
        path, lines = QPainterPath(), QPainterPath()
        for e in ents:
            pts = [QPointF(v.dxf.location.x * k, h - v.dxf.location.y * k) for v in e.vertices]
            target = path if e.is_closed else lines
            target.moveTo(pts[0])
            for q in pts[1:]:
                target.lineTo(q)
            if e.is_closed:
                target.closeSubpath()
        path.setFillRule(Qt.FillRule.WindingFill)
        p.fillPath(path, color)
        if not lines.isEmpty():
            p.strokePath(lines, color)
    p.end()
    return array(out), doc


class TestDxf(unittest.TestCase):
    def test_the_colors_aci_table_is_autocads(self):
        from ezdxf.colors import DXF_DEFAULT_COLORS
        self.assertEqual(export._ACI_HEX, "".join("%06x" % c for c in DXF_DEFAULT_COLORS))
        self.assertEqual(export.nearest_aci((255, 0, 0)), 1)
        self.assertEqual(export.nearest_aci((255, 255, 255)), 7)

    def test_dxf_matches_the_svg(self):
        for name, mode in CASES:
            svg, w, h = traced(name, mode)
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "x.dxf")
                export.write(path, svg)
                got, doc = dxf_drawn(path, w, h)
            auditor = doc.audit()
            self.assertEqual(len(auditor.errors), 0, [str(e) for e in auditor.errors])
            self.assertEqual(doc.dxfversion, "AC1009")
            # in millimeters, the picture's size at 96 to the inch
            self.assertAlmostEqual(doc.header["$EXTMAX"][0], w / 96 * 25.4, places=2)
            # a layer for each color, in the nearest AutoCAD color, the polylines on them
            colors = {"COLOR_%s" % c.upper() for c in re.findall(r"(?:fill|stroke):#([0-9a-f]{6})", svg)}
            self.assertEqual({lay.dxf.name for lay in doc.layers} - {"0", "Defpoints"}, colors)   # (ezdxf adds Defpoints)
            for lay in doc.layers:
                if lay.dxf.name.startswith("COLOR_"):
                    rgb = tuple(int(lay.dxf.name[6 + i:8 + i], 16) for i in (0, 2, 4))
                    self.assertEqual(lay.dxf.color, export.nearest_aci(rgb))
            if mode == engine.CENTERLINE:
                continue        # (lines: drawn 1 px wide here, as wide as the picture's in the SVG)
            share = off(got, drawn(svg, w, h))
            self.assertLess(share, 0.006, "%s: %.2f%% of the DXF is off" % (name, 100 * share))

    def test_curves_within_the_tolerance(self):
        # a quarter circle as a curve, 100 mm across: every point of it near the pieces
        d = "M0,100C55.228,100 100,55.228 100,0Z"
        pieces = export._flatten(d, (1.0, 1.0, 100.0), 0.025)
        self.assertEqual(len(pieces), 1)
        closed, pts = pieces[0]
        self.assertTrue(closed)
        segs = list(zip(pts, pts[1:]))
        for i in range(201):
            t = i / 200
            u = 1 - t
            x = 3 * u * u * t * 55.228 + 3 * u * t * t * 100 + t ** 3 * 100
            y = 100 - (u ** 3 * 100 + 3 * u * u * t * 100 + 3 * u * t * t * 55.228)
            near = min(_to_segment(x, y, a, b) for a, b in segs)
            self.assertLess(near, 0.025 * 1.01)
        self.assertLess(len(pts), 120)

    def test_inches(self):
        svg, w, h = traced("logo.png")
        import ezdxf
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.dxf")
            export.write(path, svg, size=export.Size(export.IN, 4))
            doc = ezdxf.readfile(path)
        self.assertAlmostEqual(doc.header["$EXTMAX"][0], 4.0)
        self.assertAlmostEqual(doc.header["$EXTMAX"][1], 4.0 * h / w, places=3)

    def test_node_count(self):
        svg = traced("smiley.png")[0]
        n = sum(len(re.findall(r"[MLC]", d)) for d in re.findall(r' d="([^"]*)"', svg))
        self.assertEqual(export.node_count(svg), n)


def _to_segment(x, y, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.run(list(args))
    return rc, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.png = os.path.join(self.tmp.name, "logo.png")
        logo().save(self.png)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_extension_picks_the_format(self):
        for fmt, magic in (("pdf", b"%PDF-1.4"), ("eps", b"%!PS-Adobe-3.0 EPSF"), ("dxf", b"  0\nSECTION"),
                           ("svg", b"<?xml")):
            out = os.path.join(self.tmp.name, "out." + fmt)
            rc, text, err = run_cli(self.png, "-o", out, "--width", "100mm")
            self.assertEqual(rc, 0, err)
            with open(out, "rb") as f:
                self.assertTrue(f.read().startswith(magic), fmt)
            self.assertIn("100 x 66.67 mm", text)
            self.assertIn(" nodes", text)

    def test_format_for_many(self):
        second = os.path.join(self.tmp.name, "two.png")
        logo(120, 80).save(second)
        folder = os.path.join(self.tmp.name, "dxfs")
        rc, _text, err = run_cli("--format", "dxf", self.png, second, "-o", folder)
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(os.listdir(folder)), ["logo.dxf", "two.dxf"])

    def test_bad_width(self):
        for bad in ("4", "4ft", "0in", "-2mm", "inch"):
            with self.assertRaises(SystemExit):
                run_cli(self.png, "--width", bad)


class TestWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.w = app.MainWindow()
        self.ini = os.path.join(self.tmp.name, "s.ini")
        self.w.qs = QSettings(self.ini, QSettings.Format.IniFormat)
        self.w.resize(1200, 800)
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

    def test_save_in_each_format(self):
        s = self.w.settings
        s.size_unit.setCurrentIndex(s.size_unit.findData(export.IN))
        s.size_width.setValue(5)
        for fmt in export.FORMATS:
            path = os.path.join(self.tmp.name, "out." + fmt)
            self.assertTrue(self.w.write(path))
        self.w.wait_saved()
        self.assertEqual(self.w.savers, [])
        svg = self.w.result.svg
        for fmt in export.FORMATS:
            with open(os.path.join(self.tmp.name, "out." + fmt), "rb") as f:
                self.assertEqual(f.read(), export.render(svg, fmt, export.Size(export.IN, 5)), fmt)
            self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "out.%s.part" % fmt)))
        self.assertIn("Saved", self.w.status.text())
        # Save again: the same file and type
        self.assertEqual(self.w.save_path, os.path.join(self.tmp.name, "out.dxf"))
        self.assertTrue(self.w.default_name().endswith(".dxf"))

    def test_a_failed_save_says_so(self):
        shown = []
        orig = app.QMessageBox.warning
        app.QMessageBox.warning = staticmethod(lambda *a: shown.append(a[2]))
        try:
            self.w.write(os.path.join(self.tmp.name, "no such folder", "x.pdf"))
            self.w.wait_saved()
        finally:
            app.QMessageBox.warning = orig
        self.assertEqual(len(shown), 1)
        self.assertIn("Couldn't save", shown[0])

    def test_saved_width_doesnt_trace_again(self):
        s = self.w.settings
        number = self.w.job_number
        self.assertEqual(s.size_info.text(), "Saved at 240 x 160 pixels (2.5 x 1.67 in)")
        self.assertFalse(s.size_width.isVisible())
        s.size_unit.setCurrentIndex(s.size_unit.findData(export.MM))
        QApplication.processEvents()
        # from pixels: the same size, in mm
        self.assertAlmostEqual(s.size_width.value(), 63.5)
        self.assertTrue(s.size_width.isVisible())
        s.size_width.setValue(200)
        s.size_unit.setCurrentIndex(s.size_unit.findData(export.IN))
        self.assertAlmostEqual(s.size_width.value(), 7.87)
        self.assertEqual(s.size_info.text(), "Saved at 7.87 x 5.25 in")
        self.assertTrue(self.traced())
        self.assertEqual(self.w.job_number, number, "the saved width traced again")
        # Copy SVG: at the saved size
        self.w.copy_svg()
        self.assertIn('width="7.87in"', QGuiApplication.clipboard().text())
        # kept for next time, and not part of Undo or Reset settings
        self.w.settings.reset_all()
        self.assertTrue(self.traced())
        self.assertEqual(s.saved_size(), export.Size(export.IN, 7.87))
        self.w.close()                          # (saves the settings)
        w2 = app.MainWindow()
        try:
            w2.qs = QSettings(self.ini, QSettings.Format.IniFormat)
            w2.settings.load(w2.qs)
            self.assertEqual(w2.settings.saved_size(), export.Size(export.IN, 7.87))
        finally:
            w2.qs = QSettings(os.path.join(self.tmp.name, "other.ini"), QSettings.Format.IniFormat)
            w2.close()

    def test_title_and_status_say_the_nodes(self):
        n = "{:,}".format(self.w.result.nodes)
        self.assertIn(n + " nodes", self.w.right.title)
        self.assertIn(n + " nodes", self.w.status.text())


if __name__ == "__main__":
    unittest.main()
