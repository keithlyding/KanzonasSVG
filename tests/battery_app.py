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
os.environ["KANZONASSVG_LANG"] = "en"   # (in English, whatever this computer's language)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeyEvent, QPainter, QPen, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication(["kanzonassvg-battery"])
if __name__ == "__main__":
    APP.setOrganizationName("Kanzonas")
    APP.setApplicationName("KanzonasSVG-battery")

from kanzonassvg import app, batch, cli, engine, export, image, tracing  # noqa: E402

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

# Dialogs (the update box) are shown, then answered with one of their buttons at random; links
# are remembered instead of opened.
from PySide6.QtGui import QDesktopServices  # noqa: E402
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPushButton  # noqa: E402

OPENED = []
DIALOG_RNG = random.Random(0)
QDesktopServices.openUrl = staticmethod(lambda url: OPENED.append(url.toString()) or True)


def _dialog_exec(self):
    self.show()
    QApplication.processEvents()
    buttons = [b for box in self.findChildren(QDialogButtonBox) for b in box.buttons()]
    if buttons:
        DIALOG_RNG.choice(buttons).click()
    self.hide()
    return 0


QDialog.exec = _dialog_exec

# Change color... and Merge's Another color...: a color at random, or Cancel
from PySide6.QtWidgets import QColorDialog  # noqa: E402

QColorDialog.getColor = staticmethod(
    lambda *a, **k: QColor() if DIALOG_RNG.random() < 0.2 else QColor(*[DIALOG_RNG.randrange(256) for _ in range(3)]))


def random_release_text(rng):
    """A release's text as anyone could write it: marks in odd places, odd lengths."""
    parts = ["<!-- kanzonas-notes -->", "<!-- /kanzonas-notes -->", "<!-- kanzonas-notes", "## heading",
             "[link](javascript:alert(1))", "<script>x</script>", "\x00", "plain words", "\n" * 3, "*" * 50]
    return "".join(rng.choice(parts) for _ in range(rng.randrange(0, 12)))


def random_releases(rng):
    """GitHub's answer as an attacker or a broken network could make it."""
    out = []
    for _ in range(rng.randrange(0, 6)):
        r = {"tag_name": rng.choice(["v99.%d" % rng.randrange(9), "v1.0", "v" + "9" * 12, "", None, 5, "v2.x",
                                     "v99.1.%d" % rng.randrange(9)])}
        if rng.random() < 0.7:
            r["body"] = random_release_text(rng) if rng.random() < 0.9 else rng.choice([None, 5, []])
        if rng.random() < 0.5:
            r["html_url"] = rng.choice(["https://github.com/keithlyding/KanzonasSVG/releases/tag/v99.1",
                                        "https://evil.example/", "javascript:alert(1)", None, 7])
        if rng.random() < 0.6:
            r["assets"] = rng.choice([[], "x", None, [{"name": n, "digest": rng.choice(["sha256:" + "ab" * 32, "x"]),
                                                       "browser_download_url": rng.choice(
                                                           ["https://github.com/a/b", "https://evil.example/a"])}
                                                      for n in ("KanzonasSVG-windows.zip",
                                                                "KanzonasSVG-x86_64.AppImage")]])
        for key in ("draft", "prerelease"):
            if rng.random() < 0.15:
                r[key] = True
        out.append(r if rng.random() < 0.95 else rng.choice(["x", 5, None]))
    return out


def update_step(rng, w, fails, seed, step):
    """A newer release found (or not), with odd release data; the notice's buttons and the update
    box answered at random. Only GitHub pages may be opened, and nothing is downloaded."""
    from kanzonassvg import updates
    u = w.updater()
    u.settings = w.qs
    u.releases = random_releases(rng)
    u.release = updates.newest_release(u.releases)
    u.manual = rng.random() < 0.4
    if u.release is not None:
        u.found.emit(updates.release_version(u.release))
    bar = getattr(w, "_update_bar", None)
    if bar is not None and rng.random() < 0.8:
        buttons = bar.findChildren(QPushButton)
        if buttons:
            rng.choice(buttons).click()
    if updates.downloading():
        fails.append("window seed %d step %d: a download started (run from source, it only tells)" % (seed, step))
    for url in OPENED:
        if not url.startswith("https://github.com/"):
            fails.append("window seed %d step %d: opened %r" % (seed, step, url))
    OPENED.clear()


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
    DIALOG_RNG.seed(seed)
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

        def answer_menus(w):
            # (every window: Reopen makes a new one) a right-click menu: one of its commands at
            # random, or none (closed); Merge's list: one of its colors, Another color..., or closed
            def answer_menu(menu, where):
                acts = [a for a in menu.actions() if not a.isSeparator() and a.isEnabled()]
                if acts and rng.random() < 0.8:
                    rng.choice(acts).trigger()
            w.open_menu = answer_menu
            w.settings.colors.open_menu = lambda menu, where: rng.choice(
                [None] + [a for a in menu.actions() if a.data() is not None])
        answer_menus(w)
        for step in range(steps):
            before = len(ERRORS)
            action = rng.choice(["open", "open", "paste", "setting", "setting", "setting", "setting", "auto",
                                 "update", "colors", "zoom", "move", "fit", "save", "copy", "reopen", "auto_new",
                                 "events", "new_version", "crop", "uncrop", "colors", "colors", "pick", "undo", "undo", "redo",
                                 "save", "saved_width", "many", "erase", "erase", "outlines", "recent",
                                 "tool", "tool", "hover", "menu", "menu", "save_as", "wheel", "ribbon"])
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
                        # in any format, at the saved size: the file is the SVG shown, converted
                        fmt = rng.choice(export.FORMATS)
                        path = os.path.join(folder, "out." + fmt)
                        svg, size = w.result.svg, w.settings.saved_size()
                        if not w.write(path):
                            fails.append("window seed %d step %d: save failed" % (seed, step))
                        w.wait_saved()
                        with open(path, "rb") as f:
                            if f.read() != export.render(svg, fmt, size):
                                fails.append("window seed %d step %d: the %s saved isn't the SVG shown at %s"
                                             % (seed, step, fmt, size))
                        if w.savers:
                            fails.append("window seed %d step %d: a save never finished" % (seed, step))
                elif action == "many":
                    # Convert many pictures: a few of the pictures, any settings, format and place
                    d = w.convert_many()
                    d.clear()
                    chosen = rng.sample(pics, rng.randrange(1, 4))
                    d.add_files(chosen)
                    (d.r_auto if rng.random() < 0.5 else d.r_shown).setChecked(True)
                    d.format.setCurrentIndex(rng.randrange(d.format.count()))
                    d.where.setCurrentIndex(1)
                    out = os.path.join(folder, "many%d" % rng.randrange(3))
                    d.folder.setText(out)
                    d.replace.setChecked(rng.random() < 0.7)
                    d.start()
                    if rng.random() < 0.2:
                        d.stop()
                    d.wait()
                    stopped = "stopped" in d.summary.text()
                    fmt = d.format.currentData()
                    for row, src in enumerate(chosen):
                        ok, text = d.results.get(row, (False, "not done"))
                        dst = batch.output_path(src, out, fmt)
                        if ok and not os.path.isfile(dst):
                            fails.append("window seed %d step %d: converted but no %s" % (seed, step, dst))
                        if not ok and not stopped and not text.startswith("skipped"):
                            fails.append("window seed %d step %d: %s: %s (%s)" % (seed, step, src, text, d.summary.text()))
                    d.close()
                elif action == "erase":
                    # a stroke anywhere (partly or wholly off the picture), any size; or all back
                    if w.img is not None:
                        if rng.random() < 0.15:
                            w.restore_picture()
                        else:
                            w.start_erasing(rng.random() < 0.8)
                            iw, ih = w.img.width(), w.img.height()
                            pts = [QPointF(rng.uniform(-0.2, 1.2) * iw, rng.uniform(-0.2, 1.2) * ih)
                                   for _ in range(rng.randrange(1, 6))]
                            w.on_erased(rng.choice([0.5, 2, 10, 60]), pts)
                elif action == "outlines":
                    w.a_outlines.trigger()
                elif action == "recent":
                    files = w.recent_files()
                    if files:
                        w.open_recent(rng.choice(files))
                    if len(w.recent_files()) > 10:
                        fails.append("window seed %d step %d: %d recent files" % (seed, step, len(w.recent_files())))
                elif action == "saved_width":
                    # another unit or width: nothing traced again
                    number, s = w.job_number, w.settings
                    if rng.random() < 0.5:
                        s.size_unit.setCurrentIndex(rng.randrange(s.size_unit.count()))
                    else:
                        s.size_width.setValue(rng.choice([0.01, 1, 4.5, 100, 2000, 100000]))
                    if w.job_number != number:
                        fails.append("window seed %d step %d: the saved width traced again" % (seed, step))
                elif action == "copy":
                    w.copy_svg()
                elif action == "reopen":
                    w.close()
                    w = app.MainWindow()
                    w.qs = QSettings(os.path.join(folder, "s.ini"), QSettings.Format.IniFormat)
                    w.show()
                    answer_menus(w)
                elif action == "crop":
                    if w.img is not None:
                        # a rectangle anywhere (partly or wholly off the picture, tiny or all of it)
                        from PySide6.QtCore import QRectF as _R
                        iw, ih = w.img.width(), w.img.height()
                        x, y = rng.uniform(-0.3, 1.1) * iw, rng.uniform(-0.3, 1.1) * ih
                        w.start_crop()
                        w.on_cropped(_R(x, y, rng.uniform(0, 1.2) * iw, rng.uniform(0, 1.2) * ih))
                        if w.crop is not None and (w.img.width(), w.img.height()) != (w.crop.width(), w.crop.height()):
                            fails.append("window seed %d step %d: cropped picture %dx%d, crop %s" % (
                                seed, step, w.img.width(), w.img.height(), w.crop))
                elif action == "colors":
                    # random swatches, then change, merge, leave out (or put back) or reset
                    c = w.settings.colors
                    for i, g in enumerate(list(c.groups)):
                        if rng.random() < 0.3:
                            c.click_group(g, add=i > 0 and rng.random() < 0.8)
                    what = rng.choice(["change", "merge", "out", "reset", "reset_all"])
                    if what == "change":
                        c.change_color(tuple(rng.randrange(256) for _ in range(3)))
                    elif what == "merge":
                        kept = [g.color for g in c._selected_groups() if not g.left_out]
                        c.merge(rng.choice(kept) if kept and rng.random() < 0.8
                                else tuple(rng.randrange(256) for _ in range(3)))
                    elif what == "out":
                        c.leave_out()
                    elif what == "reset":
                        c.reset()
                    else:
                        c.selected = set()
                        c.reset()
                    if w.settings.options().edits != c.edits_tuple():
                        fails.append("window seed %d step %d: the edits aren't in the settings" % (seed, step))
                elif action == "pick":
                    if w.img is not None:
                        from PySide6.QtCore import QPointF as _P
                        w.on_picture_clicked(_P(rng.uniform(-5, w.img.width() + 5), rng.uniform(-5, w.img.height() + 5)),
                                             rng.random() < 0.5)     # (Ctrl held, or not)
                elif action == "undo":
                    w.undo()
                elif action == "redo":
                    w.redo()
                elif action == "uncrop":
                    w.remove_crop()
                    if w.crop is not None:
                        fails.append("window seed %d step %d: Remove crop left a crop" % (seed, step))
                elif action == "tool":
                    # the tools: picked, by their commands, Esc, the eraser's size
                    how = rng.random()
                    if how < 0.4:
                        w.set_tool(rng.choice(["select", "crop", "erase"]))
                    elif how < 0.7:
                        rng.choice([w.a_select, w.a_crop, w.a_erase]).trigger()
                    elif how < 0.85:
                        w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
                    else:
                        w.eraser_slider.setValue(rng.randint(1, 500))
                    on = [w.a_select.isChecked(), w.a_crop.isChecked(), w.a_erase.isChecked()]
                    if on.count(True) != 1 or w.left.crop_mode != (w.tool == "crop") \
                            or w.left.erase_mode != (w.tool == "erase") or not 2 <= w.left.eraser <= 200:
                        fails.append("window seed %d step %d: the tools disagree: %s %s crop %s erase %s eraser %s"
                                     % (seed, step, w.tool, on, w.left.crop_mode, w.left.erase_mode, w.left.eraser))
                elif action == "hover":
                    w.on_hover(None if w.img is None or rng.random() < 0.2 else
                               QPointF(rng.uniform(-5, w.img.width() + 5), rng.uniform(-5, w.img.height() + 5)))
                elif action == "menu":
                    # a right-click on the picture, the SVG or a swatch, then one of its commands
                    c = w.settings.colors
                    if c.buttons and rng.random() < 0.3:
                        rng.choice(c.buttons).customContextMenuRequested.emit(QPoint(1, 1))
                    elif w.img is not None:
                        w.on_picture_menu(QPointF(rng.uniform(-5, w.img.width() + 5),
                                                  rng.uniform(-5, w.img.height() + 5)), QPoint(0, 0))
                elif action == "save_as":
                    # File > Save as SVG/PDF/EPS/DXF: the file written is the SVG shown, as that kind
                    fmt = rng.choice(export.FORMATS)
                    name = os.path.join(folder, "as%d" % step)
                    w.ask_save_path = lambda start, f: "" if rng.random() < 0.2 else name
                    svg, size = (w.result.svg, w.settings.saved_size()) if w.result is not None else (None, None)
                    if w.save_as(fmt):
                        w.wait_saved()
                        with open(name + "." + fmt, "rb") as f:
                            if f.read() != export.render(svg, fmt, size):
                                fails.append("window seed %d step %d: Save as %s didn't write the SVG shown"
                                             % (seed, step, fmt))
                elif action == "wheel":
                    # the wheel over the picture, the SVG or the settings panel, with or without Ctrl
                    # and Shift: never a setting it passes over
                    target = rng.choice([w.left, w.right, w.settings.speckles, w.settings.mode, w.settings.scans])
                    mods = rng.choice([Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier,
                                       Qt.KeyboardModifier.ShiftModifier])
                    options = w.settings.options()
                    pos = QPointF(rng.uniform(0, max(1, target.width())), rng.uniform(0, max(1, target.height())))
                    QApplication.sendEvent(target, QWheelEvent(pos, QPointF(target.mapToGlobal(pos.toPoint())),
                                                               QPoint(0, 0), QPoint(0, rng.choice([-360, -120, 120, 240])),
                                                               Qt.MouseButton.NoButton, mods,
                                                               Qt.ScrollPhase.NoScrollPhase, False))
                    if not target.hasFocus() and w.settings.options() != options:
                        fails.append("window seed %d step %d: the wheel changed a setting it passed over" % (seed, step))
                elif action == "ribbon":
                    r = w.ribbon
                    if rng.random() < 0.3:
                        w.a_collapse.trigger()
                    else:
                        r.setCurrentIndex(rng.randrange(r.count()))
                elif action == "new_version":
                    update_step(rng, w, fails, seed, step)
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
                if w.full_img is not None and w.img != w.picture_now():
                    fails.append("window seed %d step %d: the picture traced isn't the one opened with its erasing "
                                 "and crop" % (seed, step))
                if w.history and w.history[w.history_at] != w._state():
                    fails.append("window seed %d step %d: Undo's place isn't what's shown" % (seed, step))
                if w.job.options != w.settings.options():
                    fails.append("window seed %d step %d: the SVG shown isn't for the settings shown:\n %s\n %s"
                                 % (seed, step, w.job.options, w.settings.options()))
                expect = tracing.trace_image(w.img, w.settings.options(), w.settings.enlarge_setting()).svg
                if expect != w.result.svg:
                    fails.append("window seed %d step %d: the SVG shown differs from tracing again" % (seed, step))
                # the selected colors marked on the SVG shown (none selected: no mark)
                c = w.settings.colors
                chosen = c.selected_colors() if c.isVisible() and c.selected else []
                want = tuple(tuple(x) for x in chosen) if chosen else None
                if w.right.mark != want:
                    fails.append("window seed %d step %d: the mark isn't the selected colors (%s)" % (seed, step, chosen))
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
    try:
        check_window(args.steps, args.seed, fails)
    except BaseException:
        # (the hook above keeps exceptions quiet: one out of the steps' own checks ended the
        # run with nothing said, and Qt then aborted on the threads left running)
        fails.append("window seed %d: the battery itself stopped:\n%s" % (args.seed, traceback.format_exc()))
    for f in fails:
        print("FAIL", f)
    print("%s: %d failures in %.0f s" % ("FAILED" if fails else "PASSED", len(fails), time.time() - t))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
