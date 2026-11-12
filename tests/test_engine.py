"""The tracing engine: right colors, holes, layers, every mode, cancelling, bad input."""

import locale
import re
import unittest

from tests import helpers  # noqa: F401 (sets up Qt first)
from kanzonassvg import engine, image, tracing

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
        svg2, n2 = trace(logo(), remove_background=True)
        self.assertNotIn("#ffffff", fills(svg2))
        self.assertEqual(n2, 2)

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
