"""--selftest LOG: check the packaged app (engine found, every mode traces right, pictures
read, window opens). The build runs it inside the finished exe/AppImage."""

import os
import sys
import tempfile
import time
import traceback


def run(argv):
    log_path = argv[0] if argv else "selftest.log"
    lines = []
    failures = 0

    def log(text):
        lines.append(text)
        print(text, flush=True)

    def check(name, fn):
        nonlocal failures
        t = time.perf_counter()
        try:
            detail = fn() or ""
            log("PASS %-28s %6.2fs %s" % (name, time.perf_counter() - t, detail))
        except Exception:
            failures += 1
            log("FAIL %-28s\n%s" % (name, traceback.format_exc()))

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["kanzonassvg-selftest"])

    from kanzonassvg import __version__, engine, image, tracing

    log("KanzonasSVG %s self test, Python %s, %s" % (__version__, sys.version.split()[0], sys.platform))

    def picture():
        img = QImage(240, 160, QImage.Format.Format_RGBA8888)
        img.fill(Qt.GlobalColor.white)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(QRectF(20, 30, 70, 100), QColor(0xB2, 0x00, 0x2D))
        p.setPen(QPen(QColor(0x1D, 0x3F, 0x8F), 16))
        p.drawEllipse(QPointF(165, 80), 50, 50)
        p.end()
        return img

    def render(svg):
        r = QSvgRenderer(QByteArray(svg.encode()))
        assert r.isValid(), "invalid SVG"
        out = QImage(240, 160, QImage.Format.Format_RGBA8888)
        out.fill(Qt.GlobalColor.white)
        p = QPainter(out)
        r.render(p, QRectF(0, 0, 240, 160))
        p.end()
        return out

    img = picture()

    def engine_loads():
        return "engine " + engine.version()

    def colors_exact():
        res = tracing.trace_image(img, engine.Options(), 1)
        for c in ("#b2002d", "#1d3f8f", "#ffffff"):
            assert "fill:" + c in res.svg, c
        out = render(res.svg)
        assert out.pixelColor(165, 80).name() == "#ffffff", "the hole of the O is filled"
        assert out.pixelColor(50, 80).name() == "#b2002d", out.pixelColor(50, 80).name()
        return "%d shapes" % res.shapes

    def every_mode():
        done = []
        for mode, name in engine.MODE_NAMES.items():
            res = tracing.trace_image(img, engine.Options(mode=mode, scans=4))
            assert res.shapes > 0, name
            render(res.svg)
            done.append(name)
        return ", ".join(done)

    def reads_pictures():
        readable = set(image.supported_suffixes())
        missing = {"png", "jpg", "jpeg", "bmp", "gif", "webp", "tif", "tiff", "ico"} - readable
        assert not missing, "can't read: " + ", ".join(sorted(missing))
        with tempfile.TemporaryDirectory() as d:
            for fmt in ("png", "jpg", "bmp", "webp", "tif"):
                path = os.path.join(d, "p." + fmt)
                assert img.save(path), "can't write " + fmt
                assert image.load(path).width() == 240, fmt
        return "reads " + ", ".join(sorted(readable))

    def big_picture():
        big = img.scaled(2400, 1600)
        t = time.perf_counter()
        res = tracing.trace_image(image.to_rgba(big), engine.Options(), 1)
        secs = time.perf_counter() - t
        assert secs < 10, "too slow: %.1f s" % secs
        return "3.8 MP in %.2f s, %d shapes" % (secs, res.shapes)

    def window_opens():
        from kanzonassvg.app import MainWindow

        w = MainWindow()
        w.show()
        w.set_image(image.to_rgba(img), None)
        end = time.time() + 30
        while (w.worker is not None or w.result is None) and time.time() < end:
            app.processEvents()
            time.sleep(0.01)
        assert w.result is not None, "the window didn't trace"
        w.close()
        return w.status.text()

    def command_line():
        from kanzonassvg import cli

        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.png")
            img.save(src)
            rc = cli.run([src, "-q"])
            assert rc == 0 and os.path.exists(os.path.join(d, "a.svg")), rc
        return "ok"

    for name, fn in [("engine loads", engine_loads), ("exact colors and holes", colors_exact),
                     ("every mode", every_mode), ("reads pictures", reads_pictures),
                     ("big picture speed", big_picture), ("window opens and traces", window_opens),
                     ("command line", command_line)]:
        check(name, fn)

    log("%s: %d failed" % ("FAILED" if failures else "ALL PASSED", failures))
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if failures else 0
