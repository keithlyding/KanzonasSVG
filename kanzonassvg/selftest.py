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

    def logo_and_icon():
        here = os.path.dirname(os.path.abspath(engine.__file__))
        for name, width in (("logo.png", 1872), ("icon.png", 256)):
            q = QImage(os.path.join(here, name))
            assert not q.isNull() and q.width() == width, "%s missing or wrong (%d px)" % (name, q.width())
        return "logo and icon in the program"

    def auto_settings():
        o, info = engine.auto(*image.pixels(img))
        assert (o.mode, o.scans) == (engine.COLORS, 3), (o.mode, o.scans)
        return "%d colors in the test picture" % o.scans

    def drawing():
        # the engine's own SVG drawing (the window's): matches Qt's, and fast
        res = tracing.trace_image(img, engine.Options(), 1)
        out = QImage(240, 160, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.white)
        engine.Drawing(res.svg).render_image(out, 0, 0, 240, 160)
        qt = render(res.svg)
        for x, y in ((50, 80), (165, 30), (165, 80), (5, 5)):
            a, b = out.pixelColor(x, y), qt.pixelColor(x, y)
            assert max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) < 8, (x, y)
        return "matches Qt's"

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

    def color_edits():
        # the engine's colors, and edits on them: recolored, merged, left out
        from dataclasses import replace
        o = engine.Options(smooth=False)
        pal = engine.palette(*image.pixels(img), options=o)
        cols = [c for c, _n, _bg in pal]
        assert (0xB2, 0x00, 0x2D) in cols and (0x1D, 0x3F, 0x8F) in cols, cols
        red, blue = (0xB2, 0x00, 0x2D), (0x1D, 0x3F, 0x8F)
        svg = tracing.trace_image(img, replace(o, edits=((red, (0, 160, 0)), (blue, None))), 1).svg
        assert "fill:#00a000" in svg and "fill:#1d3f8f" not in svg and "fill:#b2002d" not in svg, svg[:300]
        out = render(svg)
        assert out.pixelColor(50, 80).name() == "#00a000", out.pixelColor(50, 80).name()
        return "%d colors; recolored and left out" % len(cols)

    def saving():
        # SVG, PDF, EPS and DXF at a size (zlib and the rest in the program), and the color groups
        from kanzonassvg import export
        svg = tracing.trace_image(img, engine.Options(smooth=False, scans=3), 1).svg
        assert svg.count('inkscape:groupmode="layer"') == 3, svg[:600]
        size = export.Size(export.MM, 100)
        sized = export.render(svg, "svg", size).decode()
        assert 'width="100mm" height="66.6667mm"' in sized, sized[:400]
        pdf = export.render(svg, "pdf", size)
        start = int(pdf.rsplit(b"startxref\n", 1)[1].split()[0])
        assert pdf.startswith(b"%PDF-1.4") and pdf[start:start + 4] == b"xref", pdf[-80:]
        import re
        import zlib
        stream = re.search(rb"stream\n(.*)\nendstream", pdf, re.S).group(1)
        ops = zlib.decompress(stream).decode()
        assert ops.count(" rg") == 3 and ops.rstrip().endswith("Q"), ops[:200]
        eps = export.render(svg, "eps", size).decode()
        assert eps.startswith("%!PS-Adobe-3.0 EPSF-3.0") and "%%BoundingBox: 0 0 284 189" in eps, eps[:200]
        dxf = export.render(svg, "dxf", size).decode()
        assert dxf.count("\nPOLYLINE\n") == dxf.count("\nSEQEND\n") > 3 and dxf.endswith("EOF\n"), dxf[-60:]
        assert "COLOR_B2002D" in dxf and "COLOR_1D3F8F" in dxf
        return "SVG, PDF, EPS, DXF; %d nodes" % export.node_count(svg)

    def converting_many():
        # File > Convert many pictures: its module in the program, and a picture through it
        from kanzonassvg import batch, export
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.png")
            assert img.save(src)
            for fmt in export.FORMATS:
                res = batch.convert(src, batch.output_path(src, d, fmt), fmt, export.Size(export.IN, 2))
                assert os.path.getsize(os.path.join(d, "a." + fmt)) > 100, fmt
            assert batch.picture_files(d) == [src], batch.picture_files(d)
        return "%d shapes, each format" % res.shapes

    def outlines_and_erasing():
        # View > Show outlines (the engine's outline drawing) and Erase on the picture
        from kanzonassvg import app as window
        svg = tracing.trace_image(img, engine.Options(smooth=False, scans=3), 1).svg
        out = QImage(240, 160, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.white)
        engine.Drawing(svg).render_outlines_image(out, 0, 0, 240, 160, True)
        dark = sum(1 for y in range(0, 160, 2) for x in range(0, 240, 2) if out.pixelColor(x, y).lightness() < 128)
        assert 20 < dark < 2000, dark                      # (lines, not filled shapes)
        erased = window.erase(img, ((10.0, ((55.0, 80.0),)),))
        assert erased.pixelColor(55, 80).alpha() == 0 and img.pixelColor(55, 80).alpha() == 255
        return "%d outline pixels (of 9600 looked at)" % dark

    def update_check():
        # the update check reaches GitHub over TLS (Qt's network backend in the program), and
        # its pieces work in the finished program
        from PySide6.QtNetwork import QSslSocket
        from kanzonassvg import updates

        assert QSslSocket.supportsSsl(), "no TLS support: the update check can't reach GitHub"
        good = {"name": updates.PORTABLE_ZIP, "digest": "sha256:" + "ab" * 32,
                "browser_download_url": "https://github.com/keithlyding/KanzonasSVG/releases/download/v99.1/x"}
        rel = [{"tag_name": "v0.1"}, {"tag_name": "v99.1", "assets": [good],
                                      "body": "x <!-- kanzonas-notes -->\nNew things\n<!-- /kanzonas-notes --> y"},
               {"tag_name": "v99.2", "draft": True}]
        r = updates.newest_release(rel)
        assert r is rel[1], r
        assert updates.asset_url(r, updates.PORTABLE_ZIP) == good["browser_download_url"]
        assert updates.asset_url(dict(r, assets=[dict(good, browser_download_url="https://evil.example/x")]),
                                 updates.PORTABLE_ZIP) is None
        assert updates.notes_since(rel)[0][:2] == ("99.1", "New things")
        with tempfile.TemporaryDirectory() as d:
            import zipfile
            z = os.path.join(d, "u.zip")
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("KanzonasSVG/KanzonasSVG.exe", "x")
                f.writestr("KanzonasSVG/_internal/a", "x")
            new = updates.unpack(z, d)
            assert os.path.isfile(os.path.join(new, "KanzonasSVG.exe"))
            assert "robocopy" in updates.swap_script(4242, new, d)
        kind = updates.update_kind()
        return "TLS %s; this copy updates %s" % (QSslSocket.sslLibraryVersionString() or "built in",
                                                 "by " + kind if kind else "by download only")

    for name, fn in [("engine loads", engine_loads), ("exact colors and holes", colors_exact),
                     ("logo and icon", logo_and_icon), ("auto settings", auto_settings), ("drawing SVGs", drawing), ("every mode", every_mode), ("reads pictures", reads_pictures),
                     ("big picture speed", big_picture), ("window opens and traces", window_opens),
                     ("command line", command_line), ("color edits", color_edits), ("saving", saving),
                     ("converting many", converting_many), ("outlines and erasing", outlines_and_erasing),
                     ("update check", update_check)]:
        check(name, fn)

    log("%s: %d failed" % ("FAILED" if failures else "ALL PASSED", failures))
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if failures else 0
