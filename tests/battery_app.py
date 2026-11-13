"""A battery to break the app from the outside: odd and broken picture files, and thousands of
random actions in the window.

    QT_QPA_PLATFORM=offscreen python tests/battery_app.py [--steps 3000] [--seed 1]

Files: every kind of picture Qt reads, in odd forms (16-bit, grayscale, palette, CMYK JPEG,
animated GIF, transparent, 1x1, 1x4000, a declared size of 100000 x 100000), and broken ones
(empty, truncated, text named .png, random bytes, a folder named .png): each opened in the
window and traced from the command line. Broken ones must give a message, never a crash, and
the window must still work after.

Window: random actions (open a picture, paste one, change any setting, Auto settings, Update
now, show the colors to trace, zoom, move, save, copy, close and open the window again), a few
events processed between them so traces start, get cancelled and finish in every order. After
each burst it waits for tracing to settle and checks: no exception anywhere, nothing still
running, and the SVG shown is the trace of the picture shown with the settings shown.
Exits 1 and names the seed and step of each failure.
"""

import argparse
import os
import random
import struct
import sys
import tempfile
import time
import traceback
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication(["kanzonassvg-battery"])
if __name__ == "__main__":
    APP.setOrganizationName("Kanzonas")
    APP.setApplicationName("KanzonasSVG-battery")

from kanzonassvg import app, cli, engine, image, tracing  # noqa: E402

ERRORS = []


def hook(kind, value, tb):
    ERRORS.append("".join(traceback.format_exception(kind, value, tb)))


sys.excepthook = hook

# Qt's warnings about the SVGs the app shows (a path cut short, a parse error) are failures too.
from PySide6.QtCore import qInstallMessageHandler  # noqa: E402

QT_WARNINGS = []


def qt_message(kind, context, text):
    if "svg" in (context.category or "") or "path" in text.lower():
        QT_WARNINGS.append(text)


qInstallMessageHandler(qt_message)

# Message boxes would wait for a click: answer them at once and remember what they said.
MESSAGES = []


def _box(kind):
    def show(parent, title, text, *a, **k):
        MESSAGES.append((kind, text))
        return QMessageBox.StandardButton.Ok
    return show


for _name in ("warning", "information", "critical", "question"):
    setattr(QMessageBox, _name, staticmethod(_box(_name)))
QMessageBox.about = staticmethod(lambda *a, **k: MESSAGES.append(("about", "")))


def picture(rng, w, h):
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(*[rng.randrange(256) for _ in range(3)]))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, rng.random() < 0.7)
    for _ in range(rng.randrange(0, 8)):
        c = QColor(*[rng.randrange(256) for _ in range(3)], 255 if rng.random() < 0.8 else rng.randrange(256))
        if rng.random() < 0.5:
            p.fillRect(QRectF(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(1, w), rng.uniform(1, h)), c)
        else:
            p.setPen(QPen(c, rng.uniform(1, 12)))
            p.drawEllipse(QPointF(rng.uniform(0, w), rng.uniform(0, h)), rng.uniform(1, w / 2 + 1),
                          rng.uniform(1, h / 2 + 1))
    p.end()
    return img


def png_header_only(path, w, h):
    """A PNG that says it is w x h but has no picture data."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IEND", b""))


def make_files(folder, rng):
    """{name: expected} where expected is "ok" or "error"."""
    files = {}
    base = picture(rng, 160, 110)

    def save(name, img, fmt=None, quality=-1):
        path = os.path.join(folder, name)
        assert img.save(path, fmt, quality), name
        files[path] = "ok"

    save("plain.png", base)
    save("photo.jpg", base, "JPG", 30)
    save("bitmap.bmp", base)
    save("picture.webp", base)
    save("picture.tif", base)
    save("gray8.png", base.convertToFormat(QImage.Format.Format_Grayscale8))
    save("gray16.png", base.convertToFormat(QImage.Format.Format_Grayscale16))
    save("deep16.png", base.convertToFormat(QImage.Format.Format_RGBA64))
    save("palette.png", base.convertToFormat(QImage.Format.Format_Indexed8))
    save("mono.png", base.convertToFormat(QImage.Format.Format_Mono))
    clear = QImage(120, 80, QImage.Format.Format_RGBA8888)
    clear.fill(Qt.GlobalColor.transparent)
    save("all-transparent.png", clear)
    one = QImage(1, 1, QImage.Format.Format_RGBA8888)
    one.fill(QColor(10, 200, 30))
    save("one-pixel.png", one)
    save("strip.png", picture(rng, 1, 4000))
    save("wide-strip.png", picture(rng, 4000, 2))
    save("unicode ñ 名前.png", base)
    # broken ones
    def raw(name, data, expected="error"):
        path = os.path.join(folder, name)
        with open(path, "wb") as f:
            f.write(data)
        files[path] = expected
    raw("empty.png", b"")
    with open(os.path.join(folder, "plain.png"), "rb") as f:
        good = f.read()
    raw("truncated.png", good[: len(good) // 2], "any")   # Qt may read part of it
    raw("text.png", b"this is not a picture\n" * 10)
    raw("random.jpg", bytes(rng.randrange(256) for _ in range(5000)))
    raw("jpeg-header-only.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00")
    png_header_only(os.path.join(folder, "huge-declared.png"), 100000, 100000)
    files[os.path.join(folder, "huge-declared.png")] = "error"
    png_header_only(os.path.join(folder, "zero-size.png"), 0, 0)
    files[os.path.join(folder, "zero-size.png")] = "error"
    os.mkdir(os.path.join(folder, "folder.png"))
    files[os.path.join(folder, "folder.png")] = "error"
    files[os.path.join(folder, "missing.png")] = "error"
    return files


def check_files(rng, fails):
    with tempfile.TemporaryDirectory() as folder:
        files = make_files(folder, rng)
        out = os.path.join(folder, "svgs")
        os.mkdir(out)
        w = app.MainWindow()
        w.show()
        for path, expected in files.items():
            name = os.path.basename(path)
            # the window
            MESSAGES.clear()
            before = len(ERRORS)
            shown = w.img
            opened = w.open_path(path)
            if opened:
                settle(w)
                # read in the background: it opened only if the window now shows it
                opened = w.img is not shown and not MESSAGES
            if len(ERRORS) > before:
                fails.append("files: %s: exception in the window" % name)
            if QT_WARNINGS:
                fails.append("files: %s: Qt: %s" % (name, QT_WARNINGS[:3]))
                QT_WARNINGS.clear()
            if expected == "error" and opened:
                fails.append("files: %s opened, but it isn't a usable picture" % name)
            if expected == "ok" and not opened:
                fails.append("files: %s didn't open: %s" % (name, MESSAGES))
            if expected == "ok" and opened and (w.result is None and "Couldn't trace" not in w.right.message):
                fails.append("files: %s: no SVG and no message" % name)
            # the command line
            try:
                rc = run_cli([path, "-o", out, "-f", "-q"])
            except BaseException as e:  # SystemExit from argparse counts too
                fails.append("files: %s: command line raised %r" % (name, e))
                continue
            svg = os.path.join(out, os.path.splitext(name)[0] + ".svg")
            if expected == "ok" and (rc != 0 or not os.path.exists(svg)):
                fails.append("files: %s: command line gave %s" % (name, rc))
            if expected == "error" and rc == 0:
                fails.append("files: %s: command line said it worked" % name)
        # the window still works after all that
        good = [p for p, e in files.items() if e == "ok"][0]
        if not w.open_path(good) or not settle(w) or w.result is None:
            fails.append("files: the window doesn't work after the broken files")
        w.close()
    return fails


def run_cli(args):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return cli.run(args)


def settle(w, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if not w.loading() and w.worker is None and not w.timer.isActive() and not w.pending:
            QApplication.processEvents()
            if not w.loading() and w.worker is None and not w.timer.isActive() and not w.pending:
                return True
        time.sleep(0.005)
    return False


def random_setting(rng, s):
    widgets = [getattr(s, n) for n in s._SAVED]
    wd = rng.choice(widgets)
    if isinstance(wd, QComboBox):
        wd.setCurrentIndex(rng.randrange(wd.count()))
    elif isinstance(wd, QCheckBox):
        wd.setChecked(not wd.isChecked())
    else:
        lo, hi = wd.minimum(), wd.maximum()
        if rng.random() < 0.2:
            wd.setValue(rng.choice([lo, hi]))
        elif isinstance(lo, int):
            wd.setValue(rng.randint(lo, min(hi, lo + 30)))
        else:
            wd.setValue(rng.uniform(lo, hi))


def check_window(steps, seed, fails):
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as folder:
        pics = []
        for k in range(6):
            path = os.path.join(folder, "p%d.png" % k)
            # (the last two big enough for the quick preview of big pictures)
            size = [(20, 15), (90, 70), (300, 240), (900, 700), (2400, 1600), (2600, 1500)][k]
            picture(rng, *size).save(path)
            pics.append(path)
        w = app.MainWindow()
        w.qs = QSettings(os.path.join(folder, "s.ini"), QSettings.Format.IniFormat)
        w.show()
        w.resize(1100, 700)
        for step in range(steps):
            before = len(ERRORS)
            action = rng.choice(["open", "open", "paste", "setting", "setting", "setting", "setting", "auto",
                                 "update", "colors", "zoom", "move", "fit", "save", "copy", "reopen", "auto_new",
                                 "events"])
            try:
                if action == "open":
                    w.open_path(rng.choice(pics))
                elif action == "paste":
                    QGuiApplication.clipboard().setImage(picture(rng, rng.randrange(1, 200), rng.randrange(1, 200)))
                    w.paste()
                elif action == "setting":
                    random_setting(rng, w.settings)
                elif action == "auto":
                    w.settings.auto.click()
                elif action == "update":
                    w.start_trace()
                elif action == "colors":
                    w.a_colors.setChecked(not w.a_colors.isChecked())
                elif action == "zoom":
                    w.view.zoom(rng.choice([0.5, 0.8, 1.25, 2.0, 7.0, 0.01]), QPointF(rng.uniform(0, 500),
                                rng.uniform(0, 500)), w.left.size())
                elif action == "move":
                    w.view.move(rng.uniform(-3000, 3000), rng.uniform(-3000, 3000))
                elif action == "fit":
                    w.view.fit(w.left.size())
                elif action == "save":
                    if w.result is not None:
                        path = os.path.join(folder, "out.svg")
                        if not w.write(path) or not os.path.exists(path):
                            fails.append("window seed %d step %d: save failed" % (seed, step))
                elif action == "copy":
                    w.copy_svg()
                elif action == "reopen":
                    w.close()
                    w = app.MainWindow()
                    w.qs = QSettings(os.path.join(folder, "s.ini"), QSettings.Format.IniFormat)
                    w.show()
                elif action == "auto_new":
                    w.a_auto_new.setChecked(not w.a_auto_new.isChecked())
                # a few events: traces start, are cancelled and finish in every order
                for _ in range(rng.choice([0, 0, 1, 3, 10])):
                    QApplication.processEvents()
                w.left.repaint()
                w.right.repaint()
            except Exception:
                ERRORS.append(traceback.format_exc())
            if len(ERRORS) > before:
                fails.append("window seed %d step %d (%s): exception:\n%s" % (seed, step, action, ERRORS[-1]))
            if QT_WARNINGS:
                fails.append("window seed %d step %d (%s): Qt: %s" % (seed, step, action, QT_WARNINGS[:3]))
                QT_WARNINGS.clear()
            # now and then: let it settle and check what's shown
            if step % 25 == 24 or step == steps - 1:
                if not settle(w):
                    fails.append("window seed %d step %d: tracing never settled" % (seed, step))
                    continue
                if w.img is None:
                    continue
                if "..." in w.status.text():
                    fails.append("window seed %d step %d: status stuck on %r" % (seed, step, w.status.text()))
                if w.result is None:
                    if "Couldn't trace" not in w.right.message:
                        fails.append("window seed %d step %d: no SVG and no message" % (seed, step))
                    continue
                if w.job.options != w.settings.options():
                    fails.append("window seed %d step %d: the SVG shown isn't for the settings shown:\n %s\n %s"
                                 % (seed, step, w.job.options, w.settings.options()))
                expect = tracing.trace_image(w.img, w.settings.options(), w.settings.enlarge_setting()).svg
                if expect != w.result.svg:
                    fails.append("window seed %d step %d: the SVG shown differs from tracing again" % (seed, step))
            if step % 500 == 499:
                print("  window: %d steps, %d failures" % (step + 1, len(fails)), flush=True)
        w.close()
    return fails


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--steps", type=int, default=3000)
    a.add_argument("--seed", type=int, default=1)
    args = a.parse_args()
    fails = []
    t = time.time()
    check_files(random.Random(args.seed), fails)
    print("files: %d failures (%.0f s)" % (len(fails), time.time() - t), flush=True)
    check_window(args.steps, args.seed, fails)
    for f in fails:
        print("FAIL", f)
    print("%s: %d failures in %.0f s" % ("FAILED" if fails else "PASSED", len(fails), time.time() - t))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
