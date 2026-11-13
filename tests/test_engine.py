"""The tracing engine: right colors, holes, layers, every mode, cancelling, bad input."""

import locale
import re
import unittest

from tests import helpers  # noqa: F401 (sets up Qt first)
from kanzonassvg import engine, image, tracing

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from tests.helpers import BLUE, RED, bad_pixels, canvas, close, color_at, logo, render

WHITE = (255, 255, 255)


def trace(img, **kw):
    data, w, h, stride = image.pixels(img)
    return engine.trace(data, w, h, stride, engine.Options(**kw))


def fills(svg):
    return re.findall(r"fill:(#[0-9a-f]{6})", svg)


class TestColors(unittest.TestCase):
    def test_exact_colors(self):
        # anti-aliased edges, 8 colors asked for a picture of 3: the 3 exact colors, no edge shades
        svg, n = trace(logo(), scans=8)
        self.assertEqual(sorted(set(fills(svg))), sorted({"#ffffff", "#b2002d", "#1d3f8f"}))
        self.assertEqual(n, 3)

    def test_looks_like_the_picture(self):
        img = logo()
        svg, _ = trace(img)
        out = render(svg, img.width(), img.height())
        self.assertLess(bad_pixels(img, out), 0.01)
        self.assertTrue(close(color_at(out, 50, 80), (0xB2, 0x00, 0x2D)))

    def test_hole_stays_open(self):
        # inside the O, between the ring and the dot: white, not filled in blue
        img = logo()
        out = render(trace(img)[0], img.width(), img.height())
        self.assertTrue(close(color_at(out, 165, 80 - 25), WHITE), color_at(out, 165, 55))
        self.assertTrue(close(color_at(out, 165, 80), (0x1D, 0x3F, 0x8F)))
        self.assertTrue(close(color_at(out, 165, 80 - 50), (0x1D, 0x3F, 0x8F)))

    def test_background_is_the_bottom_layer_and_can_go(self):
        svg, _ = trace(logo())
        self.assertEqual(fills(svg)[0], "#ffffff")
        # Remove: the white inside the ring stays (a layer under the logo)
        svg2, n2 = trace(logo(), remove_background=engine.BG_REMOVE)
        self.assertEqual(fills(svg2)[0], "#ffffff")
        self.assertEqual(n2, 3)
        # also inside: no white at all
        svg3, n3 = trace(logo(), remove_background=engine.BG_REMOVE_ALL)
        self.assertNotIn("#ffffff", fills(svg3))
        self.assertEqual(n3, 2)

    def test_more_colors_than_the_picture_has(self):
        img = canvas(50, 40)
        img.fill(RED)
        svg, n = trace(image.to_rgba(img), scans=16)
        self.assertEqual(n, 1)
        self.assertEqual(fills(svg), ["#b2002d"])

    def test_transparent_counts_as_white(self):
        from PySide6.QtCore import Qt
        img = canvas(60, 40, Qt.GlobalColor.transparent)
        for y in range(10, 30):
            for x in range(10, 30):
                img.setPixelColor(x, y, BLUE)
        svg, _ = trace(img)
        self.assertEqual(sorted(set(fills(svg))), ["#1d3f8f", "#ffffff"])

    def test_grays(self):
        svg, _ = trace(logo(), mode=engine.GRAYS, scans=3)
        for c in fills(svg):
            self.assertTrue(c[1:3] == c[3:5] == c[5:7], c)


class TestModes(unittest.TestCase):
    def test_every_mode(self):
        img = logo()
        for mode in engine.MODE_NAMES:
            with self.subTest(mode=engine.MODE_NAMES[mode]):
                svg, n = trace(img, mode=mode, scans=4)
                self.assertTrue(svg.startswith("<?xml"))
                self.assertIn('viewBox="0 0 240 160"', svg)
                self.assertGreater(n, 0)
                render(svg, 240, 160)

    def test_black_and_white(self):
        img = logo()
        svg, n = trace(img, mode=engine.BRIGHTNESS)
        self.assertEqual((n, fills(svg)), (1, ["#000000"]))
        out = render(svg, 240, 160)
        self.assertTrue(close(color_at(out, 50, 80), (0, 0, 0)))  # red is darker than 0.45
        self.assertTrue(close(color_at(out, 5, 5), WHITE))
        out = render(trace(img, mode=engine.BRIGHTNESS, invert=True)[0], 240, 160)
        self.assertTrue(close(color_at(out, 5, 5), (0, 0, 0)))

    def test_autotrace_holes_and_order(self):
        img = logo()
        svg, n = trace(img, mode=engine.AUTOTRACE, scans=8)
        out = render(svg, 240, 160)
        self.assertLess(bad_pixels(img, out), 0.02)
        self.assertTrue(close(color_at(out, 165, 55), WHITE), color_at(out, 165, 55))
        self.assertTrue(close(color_at(out, 50, 80), (0xB2, 0x00, 0x2D)))
        self.assertLessEqual(n, 4)

    def test_centerline_gives_strokes(self):
        img = canvas(200, 100)
        from PySide6.QtGui import QPainter, QPen
        p = QPainter(img)
        p.setPen(QPen(BLUE, 6))
        p.drawLine(20, 50, 180, 50)
        p.end()
        svg, n = trace(image.to_rgba(img), mode=engine.CENTERLINE)
        self.assertIn("stroke:#", svg)
        self.assertIn("fill:none", svg)


class TestNumbers(unittest.TestCase):
    def test_decimal_point_whatever_the_locale(self):
        old = locale.setlocale(locale.LC_NUMERIC)
        for name in ("de_DE.UTF-8", "de_DE.utf8", "fr_FR.UTF-8", "German_Germany.1252", "deu"):
            try:
                locale.setlocale(locale.LC_NUMERIC, name)
                break
            except locale.Error:
                continue
        else:
            self.skipTest("no locale with a decimal comma here")
        self.assertEqual(locale.localeconv()["decimal_point"], ",")
        try:
            svg, _ = trace(logo())
        finally:
            locale.setlocale(locale.LC_NUMERIC, old)
        d = re.search(r' d="([^"]*)"', svg).group(1)
        self.assertRegex(d, r"^M[0-9.,CLMZ \-]+$")
        self.assertNotRegex(d, r"\d,\d+,\d")  # a decimal comma would make x,y,z triples


class TestProgress(unittest.TestCase):
    def test_reports_and_cancels(self):
        seen = []
        data, w, h, stride = image.pixels(logo())
        engine.trace(data, w, h, stride, engine.Options(), lambda f: seen.append(f))
        self.assertTrue(seen)
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(seen, sorted(seen))
        with self.assertRaises(engine.Cancelled):
            engine.trace(data, w, h, stride, engine.Options(), lambda f: True)
        for mode in (engine.AUTOTRACE, engine.BRIGHTNESS):
            with self.assertRaises(engine.Cancelled):
                engine.trace(data, w, h, stride, engine.Options(mode=mode), lambda f: f > 0.1)


class TestInput(unittest.TestCase):
    def test_bad_input(self):
        with self.assertRaises(engine.TraceError):
            engine.trace(b"", 0, 0)
        with self.assertRaises(engine.TraceError):
            engine.trace(b"\0" * 10, 10, 10)

    def test_stride(self):
        # rows with padding at their ends
        img = logo(101, 61)
        data, w, h, stride = image.pixels(img)
        padded = b"".join(data[y * stride:y * stride + w * 4] + b"\x55" * 12 for y in range(h))
        a, _ = engine.trace(data, w, h, stride)
        b, _ = engine.trace(padded, w, h, w * 4 + 12)
        self.assertEqual(a, b)

    def test_out_of_range_options_are_clamped(self):
        svg, n = trace(logo(), scans=100000, smooth_corners=99, speckles=-5, error_threshold=-1)
        self.assertGreater(n, 0)


class TestPreview(unittest.TestCase):
    def test_preview_has_the_traced_colors(self):
        img = logo()
        data, w, h, stride = image.pixels(img)
        rgb = engine.preview(data, w, h, stride, engine.Options())
        self.assertEqual(len(rgb), w * h * 3)
        colors = {rgb[i:i + 3] for i in range(0, len(rgb), 3)}
        self.assertEqual(colors, {b"\xff\xff\xff", b"\xb2\x00\x2d", b"\x1d\x3f\x8f"})
        q = tracing.preview_image(img, engine.Options(mode=engine.BRIGHTNESS))
        self.assertEqual((q.width(), q.height()), (w, h))


class TestEnlarge(unittest.TestCase):
    def test_auto_enlarges_small_pictures_and_keeps_the_size(self):
        img = logo()
        res = tracing.trace_image(img, engine.Options())
        self.assertEqual(res.factor, 2)
        self.assertIn('width="240" height="160" viewBox="0 0 480 320"', res.svg)
        out = render(res.svg, 240, 160)
        self.assertLess(bad_pixels(img, out), 0.01)
        self.assertEqual(tracing.trace_image(img, engine.Options(), 1).factor, 1)
        self.assertEqual(tracing.enlarge_factor(tracing.AUTO, 1000, 400), 1)
        self.assertEqual(tracing.enlarge_factor(tracing.AUTO, 999, 400), 2)
        # never past MAX_ENLARGED: 4 times on a 24-megapixel photo used to build 384 megapixels
        self.assertEqual(tracing.enlarge_factor(4, 6000, 4000), 1)
        self.assertEqual(tracing.enlarge_factor(4, 3000, 2000), 2)  # 6 MP: 4x is 24 MP, 3x would be 54
        self.assertEqual(tracing.enlarge_factor(4, 1000, 1000), 4)


if __name__ == "__main__":
    unittest.main()


class TestAuto(unittest.TestCase):
    def auto(self, img):
        return engine.auto(*image.pixels(img))

    def test_logo_gets_exactly_its_colors(self):
        o, info = self.auto(logo())
        self.assertEqual((o.mode, o.scans), (engine.COLORS, 3))
        self.assertFalse(o.remove_background)
        self.assertFalse(info.photo)
        self.assertFalse(o.smooth)  # a clean picture: nothing to smooth

    def test_transparent_background_stays_transparent(self):
        from PySide6.QtCore import Qt
        img = canvas(120, 80, Qt.GlobalColor.transparent)
        for y in range(20, 60):
            for x in range(20, 100):
                img.setPixelColor(x, y, RED)
        o, info = self.auto(img)
        self.assertTrue(info.transparent)
        self.assertTrue(o.remove_background)
        svg, n = engine.trace(*image.pixels(img), options=o)
        self.assertEqual(fills(svg), ["#b2002d"])

    def test_noisy_picture_is_smoothed(self):
        import random
        rnd = random.Random(1)
        img = logo()
        for _ in range(4000):
            x, y = rnd.randrange(240), rnd.randrange(160)
            c = img.pixelColor(x, y)
            d = rnd.randint(-12, 12)
            c.setRgb(max(0, min(255, c.red() + d)), max(0, min(255, c.green() + d)), max(0, min(255, c.blue() + d)))
            img.setPixelColor(x, y, c)
        o, info = self.auto(img)
        self.assertTrue(info.noisy)
        self.assertTrue(o.smooth)
        self.assertEqual(o.scans, 3)

    def test_scan_of_dark_lines_is_black_and_white(self):
        from PySide6.QtGui import QColor, QPainter, QPen
        img = canvas(300, 200, QColor(0xF2, 0xF0, 0xEC))
        p = QPainter(img)
        p.setPen(QPen(QColor(0x2A, 0x2A, 0x2A), 7))
        p.drawLine(20, 20, 280, 180)
        p.drawEllipse(100, 40, 80, 80)
        p.end()
        o, _ = self.auto(image.to_rgba(img))
        self.assertEqual(o.mode, engine.BRIGHTNESS)
        self.assertTrue(0.3 < o.threshold < 0.8, o.threshold)

    def test_gradient_is_a_photo_with_some_colors(self):
        img = canvas(256, 64)
        for x in range(256):
            for y in range(64):
                img.setPixelColor(x, y, RED.lighter(100 + (x * 150) // 256) if y < 32 else BLUE.darker(100 + x // 2))
        o, info = self.auto(image.to_rgba(img))
        self.assertTrue(4 <= o.scans <= 16, o.scans)
        self.assertEqual(o.mode, engine.COLORS)

    def test_bad_input(self):
        with self.assertRaises(engine.TraceError):
            engine.auto(b"", 0, 0)


class TestBackground(unittest.TestCase):
    """Background: Remove leaves out the color around the picture's edge (whatever it is),
    and keeps that color inside shapes; Remove, also inside leaves it out everywhere."""

    def picture(self, page):
        # <page> all around; a red ring with the page's color inside it, and a white dot
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPainter, QPen
        img = canvas(200, 120, page)
        p = QPainter(img)
        p.setPen(QPen(RED, 14))
        p.drawEllipse(QPointF(70, 60), 40, 40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.GlobalColor.white)
        p.drawEllipse(QPointF(160, 60), 15, 15)
        p.end()
        return image.to_rgba(img)

    def render_clear(self, svg):
        from PySide6.QtCore import QByteArray, QRectF
        from PySide6.QtGui import QPainter
        from PySide6.QtSvg import QSvgRenderer
        out = canvas(200, 120, Qt.GlobalColor.transparent)
        p = QPainter(out)
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, 200, 120))
        p.end()
        return out

    def alpha(self, img, x, y):
        return img.pixelColor(x, y).alpha()

    def test_dark_background_removed_white_kept(self):
        img = self.picture(BLUE)
        svg, _ = trace(img, remove_background=engine.BG_REMOVE)
        self.assertNotIn("#1d3f8f", fills(svg)[-1:])  # not the top layer either
        out = self.render_clear(svg)
        self.assertEqual(self.alpha(out, 5, 5), 0)  # the blue page is gone
        self.assertEqual(out.pixelColor(160, 60).name(), "#ffffff")  # the white dot stays
        self.assertEqual(out.pixelColor(70, 60).name(), "#1d3f8f")  # blue inside the ring stays
        self.assertEqual(out.pixelColor(70, 20).name(), "#b2002d")
        # also inside: the blue inside the ring goes too
        out = self.render_clear(trace(img, remove_background=engine.BG_REMOVE_ALL)[0])
        self.assertEqual(self.alpha(out, 70, 60), 0)
        self.assertEqual(out.pixelColor(160, 60).name(), "#ffffff")

    def test_white_background(self):
        img = self.picture(Qt.GlobalColor.white)
        out = self.render_clear(trace(img, remove_background=engine.BG_REMOVE)[0])
        self.assertEqual(self.alpha(out, 5, 5), 0)
        self.assertEqual(out.pixelColor(70, 60).name(), "#ffffff")  # inside the ring stays white
        out = self.render_clear(trace(img, remove_background=engine.BG_REMOVE_ALL)[0])
        self.assertEqual(self.alpha(out, 70, 60), 0)
        self.assertEqual(self.alpha(out, 160, 60), 0)  # white everywhere goes
        self.assertEqual(out.pixelColor(70, 20).name(), "#b2002d")

    def test_keep(self):
        out = self.render_clear(trace(self.picture(BLUE))[0])
        self.assertEqual(out.pixelColor(5, 5).name(), "#1d3f8f")
        self.assertEqual(self.alpha(out, 5, 5), 255)

    def test_autotrace_removes_the_background_color(self):
        out = self.render_clear(trace(self.picture(BLUE), mode=engine.AUTOTRACE, remove_background=engine.BG_REMOVE)[0])
        self.assertEqual(self.alpha(out, 5, 5), 0)
        self.assertTrue(close(color_at(out, 70, 20), (0xB2, 0x00, 0x2D)), color_at(out, 70, 20))


class TestBattleFound(unittest.TestCase):
    """Bugs the batteries (tests/engine_battery.sh, tests/battery_app.py) found, kept fixed."""

    def test_not_a_number_settings(self):
        # NaN or infinite settings used to be undefined behavior in the scans
        for mode in engine.MODE_NAMES:
            o = engine.Options(mode=mode, threshold=float("nan"), smooth_corners=float("inf"),
                               optimize_tolerance=float("-inf"), error_threshold=float("nan"))
            svg, n = trace(logo(), **o.__dict__)
            self.assertTrue(svg.endswith("</svg>\n"))

    def test_autotrace_many_shapes_quickly(self):
        # Autotrace grew its lists (outlines, curves, points, splines) one element at a time:
        # time and memory traffic grew with the square of the number of shapes. A noise picture
        # in 256 colors (46,000 shapes; engine battery seed 90724, step 2292) took 147 s with
        # AddressSanitizer, 2.5 s now; without it 0.34 s -> 0.30 s here (Linux's allocator hid
        # most of it), the same SVG. Lists now double (xstd.h, XGROW).
        import time
        import numpy as np
        from PySide6.QtGui import QImage
        a = np.random.default_rng(1).integers(0, 256, (500, 600, 4), dtype=np.uint8)
        a[..., 3] = 255
        img = QImage(a.tobytes(), 600, 500, 2400, QImage.Format.Format_RGBA8888).copy()
        t = time.perf_counter()
        svg, n = trace(img, mode=engine.AUTOTRACE, scans=256, remove_background=1)
        secs = time.perf_counter() - t
        self.assertGreater(n, 100000)
        self.assertLess(secs, 5.0, "Autotrace, 160,000 shapes: %.1f s (0.9 s on Linux)" % secs)

    def test_no_near_copies_of_colors_with_smooth(self):
        # a clean picture of 3 colors, hard edges between two similar ones, Smooth on, many
        # colors asked: used to give near-copies of its colors (#33e8a2 beside #31e8a1)
        img = canvas(240, 90, QColor(0x31, 0xE8, 0xA1))
        for y in range(90):
            for x in range(240):
                if (x // 30 + y // 30) % 2:
                    img.setPixelColor(x, y, QColor(0x85, 0xF0, 0xDB))
                if 100 <= x < 140 and 30 <= y < 60:
                    img.setPixelColor(x, y, QColor(0x0A, 0x62, 0xF5))
        svg, _ = trace(img, scans=29, smooth=True)
        cols = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in set(fills(svg))]
        for a in cols:
            for b in cols:
                if a < b:
                    self.assertGreater(max(abs(p - q) for p, q in zip(a, b)), 10, (a, b))

    def test_long_paths_split_for_qt(self):
        # thousands of small shapes of one color: one <path> with more points than Qt reads (it
        # showed only part of it); now split, each <path> under the limit, and Qt reads them all
        from PySide6.QtCore import QByteArray, qInstallMessageHandler
        from PySide6.QtSvg import QSvgRenderer
        img = canvas(600, 400)
        for y in range(2, 400, 6):
            for x in range(2, 600, 6):
                for dy in range(3):
                    for dx in range(3):
                        img.setPixelColor(x + dx, y + dy, BLUE)
        svg, n = trace(img, mode=engine.BRIGHTNESS)
        self.assertGreater(n, 1)
        for d in re.findall(r' d="([^"]*)"', svg):
            points = d.count("M") + d.count("L") + 3 * d.count("C") + d.count("Z")
            self.assertLessEqual(points, 20000)
        said = []
        old = qInstallMessageHandler(lambda kind, ctx, text: said.append(text))
        try:
            QSvgRenderer(QByteArray(svg.encode()))
        finally:
            qInstallMessageHandler(old)
        self.assertEqual(said, [])

    def test_the_viewer_reads_a_shape_with_thousands_of_holes(self):
        # one outline with thousands of holes can't be split: the app's viewer reads it whole
        from PySide6.QtCore import qInstallMessageHandler
        from kanzonassvg.app import svg_renderer
        img = canvas(600, 400, QColor(0, 0, 0))
        for y in range(4, 396, 5):
            for x in range(4, 596, 5):
                for dy in range(2):
                    for dx in range(2):
                        img.setPixelColor(x + dx, y + dy, QColor(255, 255, 255))
        svg, _ = trace(img, mode=engine.BRIGHTNESS)
        said = []
        old = qInstallMessageHandler(lambda kind, ctx, text: said.append(text))
        try:
            r = svg_renderer(svg)
        finally:
            qInstallMessageHandler(old)
        self.assertTrue(r.isValid())
        self.assertEqual(said, [])
