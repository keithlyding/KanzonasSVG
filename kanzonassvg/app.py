"""The KanzonasSVG window: open a picture, pick settings, see the SVG beside it, save it."""

import os
import sys
from dataclasses import replace

from PySide6.QtCore import QByteArray, QMimeData, QObject, QRectF, QSettings, QSize, Qt, QThread, \
    QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, \
    QFileDialog, QFormLayout, QGroupBox, QLabel, QMainWindow, QMessageBox, QProgressBar, \
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from kanzonassvg import APP_NAME, __version__, engine, image, tracing

# (label, engine mode)
MODES = [
    ("Colors", engine.COLORS),
    ("Grays", engine.GRAYS),
    ("Brightness steps", engine.BRIGHTNESS_STEPS),
    ("Black and white", engine.BRIGHTNESS),
    ("Edges", engine.EDGES),
    ("Autotrace: colors", engine.AUTOTRACE),
    ("Autotrace: centerline", engine.CENTERLINE),
]
POTRACE_MODES = {engine.COLORS, engine.GRAYS, engine.BRIGHTNESS_STEPS, engine.BRIGHTNESS, engine.EDGES}
MULTI_MODES = {engine.COLORS, engine.GRAYS, engine.BRIGHTNESS_STEPS}
AUTOTRACE_MODES = {engine.AUTOTRACE, engine.CENTERLINE}

PICTURE_FILTER = "Pictures (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.ico);;All files (*)"

HELP_HTML = """
<h2>KanzonasSVG</h2>
<p>KanzonasSVG turns a picture (a logo, a drawing, a scan) into an SVG file: shapes
instead of pixels, sharp at any size. Edit the SVG afterwards in Inkscape, Illustrator
or another vector editor.</p>
<h3>Making an SVG</h3>
<ol>
<li><b>Open a picture</b>: <i>File &gt; Open picture...</i> (Ctrl+O), drag a file into the
window, or copy a picture and use <i>File &gt; Paste picture</i> (Ctrl+V).</li>
<li><b>Check the settings</b> on the right. When you open a picture, KanzonasSVG picks the
settings that suit it (see <b>Auto settings</b> below) and traces it. Change any setting and
the SVG on the right side of the window updates (unless <i>Trace &gt; Update automatically</i>
is off: then press <i>Trace &gt; Update now</i>, F5).</li>
<li><b>Save</b>: <i>File &gt; Save SVG...</i> (Ctrl+S), or <i>File &gt; Copy SVG</i>
(Ctrl+Shift+C) to paste it straight into Inkscape or another program.</li>
</ol>
<h3>Auto settings</h3>
<p>The <b>Auto settings</b> button (or <i>Trace &gt; Auto settings</i>, Ctrl+Shift+A) picks the
settings for the picture: how many colors it needs (the fewest after which more colors no
longer make it visibly closer: a logo gets exactly its colors, a photo or painting a number
that keeps the file reasonable), <b>Smooth</b> when it has JPEG blotches or scan noise,
<b>Remove background</b> when its background is transparent (so the SVG's is too), and
<b>Black and white</b> with its <b>Threshold</b> for a scan of dark lines on a light page.
The status bar says what it picked. Change anything after: Auto doesn't change it back.</p>
<p><i>Trace &gt; Auto settings for new pictures</i> (on at first) does this for every picture you
open or paste; turn it off to keep your own settings for each new picture.</p>
<h3>Modes</h3>
<ul>
<li><b>Colors</b>: the picture in a few flat colors, one layer per color. Best for logos.
<b>Colors</b> sets how many (count the background too: a red logo on white is 2).</li>
<li><b>Grays</b>: the same in shades of gray.</li>
<li><b>Brightness steps</b>: layers of gray by brightness, from dark to light.</li>
<li><b>Black and white</b>: one black shape for everything darker than <b>Threshold</b>.</li>
<li><b>Edges</b>: the outlines of shapes, found by edge detection.</li>
<li><b>Autotrace: colors</b>: colors traced with Autotrace instead of Potrace: fewer,
looser curves.</li>
<li><b>Autotrace: centerline</b>: lines along the middle of strokes (handwriting, line art)
instead of outlines.</li>
</ul>
<h3>Settings</h3>
<ul>
<li><b>Smooth</b>: evens out noise, JPEG blotches and texture before the colors are picked,
while keeping edges sharp.</li>
<li><b>Stack</b>: each color layer also covers the area of the layers above it, so no gaps
show between colors. Off: the layers are tiled side by side.</li>
<li><b>Remove background</b>: leaves out the bottom layer (usually the background).</li>
<li><b>Invert</b>: traces the light parts instead of the dark ones.</li>
<li><b>Speckles</b>: drops spots of up to this many pixels.</li>
<li><b>Smooth corners</b>: 0 keeps every corner sharp; higher rounds them off.</li>
<li><b>Optimize</b>: joins curve segments (smaller files); <b>Tolerance</b> is how far that may
move the curve.</li>
<li><b>Error threshold</b> and <b>Filter passes</b> (Autotrace): how closely curves follow
the outline, and how much outlines are smoothed first.</li>
<li><b>Keep line widths</b> (centerline): gives each line its width in the picture.</li>
<li><b>Enlarge first</b>: traces the picture at 2 or 4 times its size, for smoother curves on
small pictures. <i>Auto</i> does 2 times for pictures under 1000 pixels. The SVG keeps the
picture's size either way.</li>
</ul>
<p>The settings are kept for next time. <i>Trace &gt; Reset settings</i> (or the
<b>Reset settings</b> button) puts them all back to how they started.</p>
<h3>Looking at it</h3>
<p>The left side shows the picture; <i>View &gt; Show colors to trace</i> (Ctrl+T) shows it
with its colors reduced, as it will be traced. Both sides zoom and move together: turn the
mouse wheel to zoom, drag to move. <i>View &gt; Zoom to fit</i> (Ctrl+0), <i>View &gt; Actual
size</i> (Ctrl+1), <i>View &gt; Zoom in</i> (Ctrl++), <i>View &gt; Zoom out</i> (Ctrl+-).</p>
<h3>Keyboard shortcuts</h3>
<table cellpadding="2">
<tr><td>Ctrl+O</td><td>Open picture</td></tr>
<tr><td>Ctrl+V</td><td>Paste picture</td></tr>
<tr><td>Ctrl+S</td><td>Save SVG</td></tr>
<tr><td>Ctrl+Shift+S</td><td>Save SVG as</td></tr>
<tr><td>Ctrl+Shift+C</td><td>Copy SVG</td></tr>
<tr><td>F5</td><td>Update now</td></tr>
<tr><td>Ctrl+Shift+A</td><td>Auto settings</td></tr>
<tr><td>Ctrl+T</td><td>Show colors to trace</td></tr>
<tr><td>Ctrl+0 / Ctrl+1</td><td>Zoom to fit / Actual size</td></tr>
<tr><td>Ctrl++ / Ctrl+-</td><td>Zoom in / Zoom out</td></tr>
<tr><td>F1</td><td>How to use KanzonasSVG</td></tr>
<tr><td>Ctrl+Q</td><td>Quit</td></tr>
</table>
<h3>Command line</h3>
<p>The same tracing works from a command prompt, for many files at once (on Windows,
<code>kanzonassvg-cli.exe</code> in the program's folder). Run it with <code>--help</code> to
see every option, for example:<br>
<code>kanzonassvg-cli --colors 4 *.png -o svgs</code></p>
<h3>About</h3>
<p><i>Help &gt; About KanzonasSVG</i> shows the version, where the tracing comes from, and the
license.</p>
"""


class View(QObject):
    """Zoom and position, shared by both sides so they move together."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.scale = 1.0  # screen pixels per picture pixel
        self.cx = 0.0  # picture point at the middle of the view
        self.cy = 0.0
        self.width = 0  # picture size
        self.height = 0
        self.fitted = True

    def set_picture(self, w, h):
        self.width, self.height = w, h
        self.cx, self.cy = w / 2, h / 2

    def fit(self, size):
        if not self.width or size.width() < 2 or size.height() < 2:
            return
        self.scale = min(size.width() / self.width, size.height() / self.height) * 0.95
        self.cx, self.cy = self.width / 2, self.height / 2
        self.fitted = True
        self.changed.emit()

    def zoom(self, factor, anchor=None, size=None):
        new = max(0.01, min(64.0, self.scale * factor))
        if anchor is not None and size is not None:
            # keep the picture point under the cursor where it is
            px = self.cx + (anchor.x() - size.width() / 2) / self.scale
            py = self.cy + (anchor.y() - size.height() / 2) / self.scale
            self.cx = px - (anchor.x() - size.width() / 2) / new
            self.cy = py - (anchor.y() - size.height() / 2) / new
        self.scale = new
        self.fitted = False
        self.changed.emit()

    def move(self, dx, dy):
        self.cx -= dx / self.scale
        self.cy -= dy / self.scale
        self.fitted = False
        self.changed.emit()

    def target(self, size):
        """Where the whole picture goes in a widget of <size>."""
        x = size.width() / 2 - self.cx * self.scale
        y = size.height() / 2 - self.cy * self.scale
        return QRectF(x, y, self.width * self.scale, self.height * self.scale)


class Canvas(QWidget):
    """One side: the picture, or the SVG."""

    def __init__(self, view, title):
        super().__init__()
        self.view = view
        self.title = title
        self.picture = None  # QImage
        self.renderer = None  # QSvgRenderer
        self.message = ""
        self.cache = None  # (key, QImage) of the SVG drawn at the current view
        self.drag = None
        self.setMinimumSize(200, 200)
        self.setMouseTracking(False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        view.changed.connect(self.update)
        self.redraw = QTimer(self, singleShot=True, interval=120)
        self.redraw.timeout.connect(self._render_svg)

    def set_picture(self, img):
        self.picture, self.renderer, self.cache = img, None, None
        self.update()

    def set_svg(self, svg):
        self.picture = None
        self.renderer = QSvgRenderer(QByteArray(svg.encode("utf-8"))) if svg else None
        self.cache = None
        self.update()
        self._render_svg()

    def set_message(self, text):
        self.message = text
        self.update()

    def _key(self):
        return (self.view.scale, self.view.cx, self.view.cy, self.width(), self.height(), self.devicePixelRatioF())

    def _render_svg(self):
        if not self.renderer or not self.renderer.isValid():
            return
        dpr = self.devicePixelRatioF()
        img = QImage(QSize(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr))),
                     QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.renderer.render(p, self.view.target(self.size()))
        p.end()
        self.cache = (self._key(), img, self.view.scale, self.view.cx, self.view.cy)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        self._checkers(p)
        if self.picture is not None and not self.picture.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.view.scale < 2)
            p.drawImage(self.view.target(self.size()), self.picture)
        elif self.renderer is not None and self.cache is not None:
            key, img, scale, cx, cy = self.cache
            if key == self._key():
                p.drawImage(0, 0, img)
            else:
                # moved or zoomed since it was drawn: show it shifted, draw it again shortly
                f = self.view.scale / scale
                w, h = self.width(), self.height()
                left = w / 2 + (cx - self.view.cx) * self.view.scale - w / 2 * f
                top = h / 2 + (cy - self.view.cy) * self.view.scale - h / 2 * f
                p.drawImage(QRectF(left, top, w * f, h * f), img)
                self.redraw.start()
        elif self.renderer is not None:
            self.redraw.start()
        if self.message:
            p.setPen(self.palette().color(QPalette.ColorRole.Text))
            p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.message)
        p.setPen(QColor(90, 90, 90))
        p.drawText(8, 18, self.title)
        p.end()

    def _checkers(self, p):
        """The window color around the picture, a checkerboard (transparent) under it."""
        p.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
        if self.picture is None and self.renderer is None:
            return
        r = self.view.target(self.size()).intersected(QRectF(self.rect()))
        if r.isEmpty():
            return
        p.save()
        p.setClipRect(r)
        p.fillRect(r, QColor(255, 255, 255))
        s = 10
        c = QColor(232, 232, 232)
        for y in range(int(r.top()) // s * s, int(r.bottom()) + s, s):
            for x in range(int(r.left()) // (2 * s) * (2 * s) + ((y // s) % 2) * s, int(r.right()) + s, 2 * s):
                p.fillRect(x, y, s, s, c)
        p.restore()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps:
            self.view.zoom(1.25 ** steps, e.position(), self.size())

    def mousePressEvent(self, e):
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.drag = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            d = e.position() - self.drag
            self.drag = e.position()
            self.view.move(d.x(), d.y())

    def mouseReleaseEvent(self, _e):
        self.drag = None
        self.unsetCursor()

    def resizeEvent(self, e):
        if self.view.fitted:
            self.view.fit(self.size())
        super().resizeEvent(e)


class Job:
    def __init__(self, number, img, options, enlarge, want_preview, auto=False):
        self.number = number
        self.auto = auto  # pick the settings first (Auto settings)
        self.auto_info = None
        self.img = img
        self.options = options
        self.enlarge = enlarge
        self.want_preview = want_preview
        self.cancelled = False


class Worker(QThread):
    """Traces in the background (the engine doesn't hold Python's lock while it works)."""

    progress = Signal(int, float)
    auto_done = Signal(int, object, object)  # job number, Options picked, engine.AutoInfo
    done = Signal(int, object, object)  # job number, Result, preview QImage or None
    failed = Signal(int, str)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        job = self.job
        try:
            last = [0.0]

            def report(f):
                if f - last[0] >= 0.02:
                    last[0] = f
                    self.progress.emit(job.number, f)
                return job.cancelled

            if job.auto:
                job.options, job.auto_info = auto_options(job.img, job.options)
                self.auto_done.emit(job.number, job.options, job.auto_info)
            preview = tracing.preview_image(job.img, job.options) if job.want_preview else None
            if job.cancelled:
                raise engine.Cancelled()
            result = tracing.trace_image(job.img, job.options, job.enlarge, report)
            self.done.emit(job.number, result, preview)
        except engine.Cancelled:
            self.failed.emit(job.number, "")
        except Exception as e:  # shown in the window, never a crash
            self.failed.emit(job.number, str(e) or e.__class__.__name__)


def auto_options(img, current):
    """The settings Auto picks for <img>: mode, colors, smoothing, background, threshold
    (the curve settings stay as they are). Returns (Options, engine.AutoInfo)."""
    picked, info = engine.auto(*image.pixels(img))
    return replace(current, mode=picked.mode, scans=picked.scans, smooth=picked.smooth,
                   remove_background=picked.remove_background, threshold=picked.threshold,
                   stack=True, invert=False), info


def describe_auto(options, info):
    """What Auto picked, in a few words for the status bar."""
    if options.mode == engine.BRIGHTNESS:
        parts = ["black and white"]
    else:
        parts = ["%d colors" % options.scans]
        if info.photo:
            parts[0] += " (a photo or painting: it has more)"
    if options.smooth:
        parts.append("smoothed")
    if options.remove_background:
        parts.append("transparent background kept")
    return "Auto: " + ", ".join(parts)


class Settings(QScrollArea):
    """The settings panel."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMinimumWidth(270)
        box = QWidget()
        lay = QVBoxLayout(box)

        self.auto = QPushButton("Auto settings")
        self.auto.setToolTip("Pick the settings that suit this picture (you can change them after)")
        lay.addWidget(self.auto)

        self.mode = QComboBox()
        for label, mode in MODES:
            self.mode.addItem(label, mode)
        top = QFormLayout()
        top.addRow("Mode", self.mode)
        lay.addLayout(top)

        self.g_multi = QGroupBox("Layers")
        f = QFormLayout(self.g_multi)
        self.scans = QSpinBox(minimum=2, maximum=64, value=8)
        self.scans.setToolTip("How many colors (count the background too)")
        self.scans_label = QLabel("Colors")
        f.addRow(self.scans_label, self.scans)
        self.smooth = QCheckBox("Smooth", checked=True)
        self.smooth.setToolTip("Even out noise and JPEG blotches first; edges stay sharp")
        self.stack = QCheckBox("Stack", checked=True)
        self.stack.setToolTip("Each layer also covers the layers above it, so no gaps show")
        self.remove_bg = QCheckBox("Remove background")
        self.remove_bg.setToolTip("Leave out the bottom layer")
        for w in (self.smooth, self.stack, self.remove_bg):
            f.addRow(w)
        lay.addWidget(self.g_multi)

        self.g_single = QGroupBox("Scan")
        f = QFormLayout(self.g_single)
        self.threshold = QDoubleSpinBox(minimum=0.0, maximum=1.0, singleStep=0.05, decimals=2, value=0.45)
        self.threshold.setToolTip("Black and white: everything darker than this is traced.\n"
                                  "Edges: higher finds fewer edges.")
        self.invert = QCheckBox("Invert")
        self.invert.setToolTip("Trace the light parts instead")
        f.addRow("Threshold", self.threshold)
        f.addRow(self.invert)
        lay.addWidget(self.g_single)

        self.g_potrace = QGroupBox("Curves")
        f = QFormLayout(self.g_potrace)
        self.speckles = QSpinBox(minimum=0, maximum=1000, value=2)
        self.speckles.setToolTip("Drop spots of up to this many pixels")
        self.corners = QDoubleSpinBox(minimum=0.0, maximum=1.34, singleStep=0.1, decimals=2, value=1.0)
        self.corners.setToolTip("0 keeps every corner sharp; higher rounds them off")
        self.optimize = QCheckBox("Optimize", checked=True)
        self.optimize.setToolTip("Join curve segments: smaller files")
        self.tolerance = QDoubleSpinBox(minimum=0.0, maximum=5.0, singleStep=0.1, decimals=2, value=0.2)
        self.tolerance.setToolTip("How far joining segments may move the curve")
        f.addRow("Speckles", self.speckles)
        f.addRow("Smooth corners", self.corners)
        f.addRow(self.optimize)
        f.addRow("Tolerance", self.tolerance)
        lay.addWidget(self.g_potrace)

        self.g_auto = QGroupBox("Autotrace")
        f = QFormLayout(self.g_auto)
        self.error = QDoubleSpinBox(minimum=0.1, maximum=10.0, singleStep=0.25, decimals=2, value=2.0)
        self.error.setToolTip("How far a curve may be from the outline, in pixels")
        self.filters = QSpinBox(minimum=0, maximum=20, value=4)
        self.filters.setToolTip("Smoothing passes on outlines before fitting curves")
        self.width = QCheckBox("Keep line widths", checked=True)
        f.addRow("Error threshold", self.error)
        f.addRow("Filter passes", self.filters)
        f.addRow(self.width)
        lay.addWidget(self.g_auto)

        g = QGroupBox("Size")
        f = QFormLayout(g)
        self.enlarge = QComboBox()
        self.enlarge.addItem("Auto", tracing.AUTO)
        self.enlarge.addItem("Off", 1)
        self.enlarge.addItem("2 times", 2)
        self.enlarge.addItem("4 times", 4)
        self.enlarge.setToolTip("Trace small pictures bigger, for smoother curves (the SVG keeps the picture's size)")
        f.addRow("Enlarge first", self.enlarge)
        lay.addWidget(g)

        self.reset = QPushButton("Reset settings")
        lay.addWidget(self.reset)
        lay.addStretch(1)
        self.setWidget(box)

        self._edge = 0.65
        self._bw = 0.45
        self._last_mode = engine.COLORS
        for w in (self.mode, self.enlarge):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.scans, self.speckles, self.filters):
            w.valueChanged.connect(self._changed)
        for w in (self.threshold, self.corners, self.tolerance, self.error):
            w.valueChanged.connect(self._changed)
        for w in (self.smooth, self.stack, self.remove_bg, self.invert, self.optimize, self.width):
            w.toggled.connect(self._changed)
        self.reset.clicked.connect(self.reset_all)
        self._update_visible()

    def current_mode(self):
        return self.mode.currentData()

    def _changed(self, *_):
        mode = self.current_mode()
        if mode != self._last_mode:
            # each of Black and white and Edges keeps its own threshold
            if self._last_mode == engine.EDGES:
                self._edge = self.threshold.value()
            elif self._last_mode == engine.BRIGHTNESS:
                self._bw = self.threshold.value()
            self._last_mode = mode
            if mode in (engine.EDGES, engine.BRIGHTNESS):
                self.threshold.blockSignals(True)
                self.threshold.setValue(self._edge if mode == engine.EDGES else self._bw)
                self.threshold.blockSignals(False)
            self._update_visible()
        self.tolerance.setEnabled(self.optimize.isChecked())
        self.changed.emit()

    def _update_visible(self):
        mode = self.current_mode()
        self.g_multi.setVisible(mode in MULTI_MODES or mode == engine.AUTOTRACE)
        self.smooth.setVisible(mode in (engine.COLORS, engine.GRAYS))
        self.stack.setVisible(mode in MULTI_MODES)
        self.remove_bg.setVisible(mode in MULTI_MODES)
        self.scans_label.setText({engine.GRAYS: "Grays", engine.BRIGHTNESS_STEPS: "Steps"}.get(mode, "Colors"))
        self.g_single.setVisible(mode in (engine.BRIGHTNESS, engine.EDGES))
        self.g_potrace.setVisible(mode in POTRACE_MODES)
        self.g_auto.setVisible(mode in AUTOTRACE_MODES)
        self.width.setVisible(mode == engine.CENTERLINE)

    def options(self):
        return engine.Options(
            mode=self.current_mode(),
            scans=self.scans.value(),
            smooth=self.smooth.isChecked(),
            stack=self.stack.isChecked(),
            remove_background=self.remove_bg.isChecked(),
            threshold=self.threshold.value(),
            invert=self.invert.isChecked(),
            speckles=self.speckles.value(),
            smooth_corners=self.corners.value(),
            optimize=self.optimize.isChecked(),
            optimize_tolerance=self.tolerance.value(),
            error_threshold=self.error.value(),
            filter_iterations=self.filters.value(),
            preserve_width=self.width.isChecked(),
        )

    def enlarge_setting(self):
        return self.enlarge.currentData()

    # saved between runs
    _SAVED = ["mode", "scans", "smooth", "stack", "remove_bg", "threshold", "invert", "speckles", "corners",
              "optimize", "tolerance", "error", "filters", "width", "enlarge"]

    def _widgets(self):
        return [(name, getattr(self, name)) for name in self._SAVED]

    def save(self, qs):
        for name, w in self._widgets():
            if isinstance(w, QComboBox):
                qs.setValue("settings/" + name, w.currentIndex())
            elif isinstance(w, QCheckBox):
                qs.setValue("settings/" + name, int(w.isChecked()))
            else:
                qs.setValue("settings/" + name, w.value())
        qs.setValue("settings/edge_threshold", self._edge if self.current_mode() != engine.EDGES
                    else self.threshold.value())
        qs.setValue("settings/bw_threshold", self._bw if self.current_mode() != engine.BRIGHTNESS
                    else self.threshold.value())

    def load(self, qs):
        for name, w in self._widgets():
            v = qs.value("settings/" + name)
            if v is None:
                continue
            w.blockSignals(True)
            try:
                if isinstance(w, QComboBox):
                    i = int(v)
                    if 0 <= i < w.count():
                        w.setCurrentIndex(i)
                elif isinstance(w, QCheckBox):
                    w.setChecked(bool(int(v)))
                elif isinstance(w, QSpinBox):
                    w.setValue(int(float(v)))
                else:
                    w.setValue(float(v))
            except (TypeError, ValueError):
                pass
            w.blockSignals(False)
        try:
            self._edge = float(qs.value("settings/edge_threshold", self._edge))
            self._bw = float(qs.value("settings/bw_threshold", self._bw))
        except (TypeError, ValueError):
            pass
        self._last_mode = self.current_mode()
        self.tolerance.setEnabled(self.optimize.isChecked())
        self._update_visible()

    def apply_auto(self, o):
        """Show the settings Auto picked (without tracing again: they're being traced)."""
        widgets = [w for _, w in self._widgets()]
        for w in widgets:
            w.blockSignals(True)
        index = [m for _, m in MODES].index(o.mode)
        self.mode.setCurrentIndex(index)
        self.scans.setValue(max(self.scans.minimum(), min(self.scans.maximum(), o.scans)))
        self.smooth.setChecked(o.smooth)
        self.stack.setChecked(o.stack)
        self.remove_bg.setChecked(o.remove_background)
        self.invert.setChecked(o.invert)
        if o.mode == engine.BRIGHTNESS:
            self.threshold.setValue(o.threshold)
            self._bw = o.threshold
        elif o.mode == engine.EDGES:
            self.threshold.setValue(self._edge)
        for w in widgets:
            w.blockSignals(False)
        self._last_mode = o.mode
        self._update_visible()

    def reset_all(self):
        widgets = [w for _, w in self._widgets()]
        for w in widgets:
            w.blockSignals(True)
        self.mode.setCurrentIndex(0)
        self.scans.setValue(8)
        self.smooth.setChecked(True)
        self.stack.setChecked(True)
        self.remove_bg.setChecked(False)
        self.threshold.setValue(0.45)
        self.invert.setChecked(False)
        self.speckles.setValue(2)
        self.corners.setValue(1.0)
        self.optimize.setChecked(True)
        self.tolerance.setValue(0.2)
        self.error.setValue(2.0)
        self.filters.setValue(4)
        self.width.setChecked(True)
        self.enlarge.setCurrentIndex(0)
        for w in widgets:
            w.blockSignals(False)
        self._edge, self._bw, self._last_mode = 0.65, 0.45, engine.COLORS
        self.tolerance.setEnabled(True)
        self._update_visible()
        self.changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.qs = QSettings("Kanzonas", APP_NAME)
        self.img = None  # QImage, RGBA8888
        self.source_path = None
        self.save_path = None
        self.result = None  # tracing.Result
        self.preview = None  # QImage
        self.job_number = 0
        self.job = None
        self.worker = None
        self.pending = False
        self.pending_auto = False
        self.closing = False

        self.view = View()
        self.left = Canvas(self.view, "Picture")
        self.right = Canvas(self.view, "SVG")
        self.left.set_message("Open a picture (Ctrl+O), drag one here, or paste one (Ctrl+V).")
        split = QSplitter()
        split.addWidget(self.left)
        split.addWidget(self.right)
        split.setChildrenCollapsible(False)
        self.settings = Settings()
        outer = QSplitter()
        outer.addWidget(split)
        outer.addWidget(self.settings)
        outer.setStretchFactor(0, 1)
        outer.setStretchFactor(1, 0)
        self.setCentralWidget(outer)

        self.status = QLabel()
        self.bar = QProgressBar(maximum=1000, textVisible=False)
        self.bar.setFixedWidth(160)
        self.bar.hide()
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.bar)

        self.timer = QTimer(self, singleShot=True, interval=250)
        self.timer.timeout.connect(self.start_trace)
        self.settings.changed.connect(self.settings_changed)
        self.settings.auto.clicked.connect(self.auto_settings)
        self.settings.load(self.qs)

        self._make_menus()
        self.setAcceptDrops(True)
        self.resize(1300, 800)
        geo = self.qs.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._update_title()
        self._update_actions()

    # menus

    def _action(self, menu, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _make_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._action(m, "Open picture...", self.open_dialog, QKeySequence.StandardKey.Open)
        self.a_paste = self._action(m, "Paste picture", self.paste, QKeySequence.StandardKey.Paste)
        m.addSeparator()
        self.a_save = self._action(m, "Save SVG...", self.save, QKeySequence.StandardKey.Save)
        self.a_save_as = self._action(m, "Save SVG as...", self.save_as, "Ctrl+Shift+S")
        self.a_copy = self._action(m, "Copy SVG", self.copy_svg, "Ctrl+Shift+C")
        m.addSeparator()
        self._action(m, "Quit", self.close, QKeySequence.StandardKey.Quit)

        m = mb.addMenu("&View")
        self.a_colors = self._action(m, "Show colors to trace", self.show_colors_changed, "Ctrl+T", True)
        m.addSeparator()
        self._action(m, "Zoom in", lambda: self.view.zoom(1.25), QKeySequence.StandardKey.ZoomIn)
        self._action(m, "Zoom out", lambda: self.view.zoom(0.8), QKeySequence.StandardKey.ZoomOut)
        self._action(m, "Zoom to fit", lambda: self.view.fit(self.left.size()), "Ctrl+0")
        self._action(m, "Actual size", self.actual_size, "Ctrl+1")

        m = mb.addMenu("&Trace")
        self.a_auto = self._action(m, "Update automatically", self.auto_changed, None, True)
        self.a_auto.setChecked(bool(int(self.qs.value("trace/auto", 1))))
        self._action(m, "Update now", lambda: self.start_trace(), "F5")
        m.addSeparator()
        self._action(m, "Auto settings", self.auto_settings, "Ctrl+Shift+A")
        self.a_auto_new = self._action(m, "Auto settings for new pictures", self.auto_new_changed, None, True)
        self.a_auto_new.setChecked(bool(int(self.qs.value("trace/auto_new", 1))))
        self._action(m, "Reset settings", self.settings.reset_all)

        m = mb.addMenu("&Help")
        self._action(m, "How to use KanzonasSVG", self.show_help, QKeySequence.StandardKey.HelpContents)
        self._action(m, "About KanzonasSVG", self.about)

    def _update_actions(self):
        has = self.result is not None
        self.a_save.setEnabled(has)
        self.a_save_as.setEnabled(has)
        self.a_copy.setEnabled(has)

    def _update_title(self):
        name = os.path.basename(self.source_path) if self.source_path else None
        self.setWindowTitle("%s - %s" % (name, APP_NAME) if name else APP_NAME)

    # opening

    def open_dialog(self):
        start = self.qs.value("paths/open", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, "Open picture", start, PICTURE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            img = image.load(path)
        except image.ImageError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return False
        self.qs.setValue("paths/open", os.path.dirname(os.path.abspath(path)))
        self.set_image(img, os.path.abspath(path))
        return True

    def paste(self):
        md = QGuiApplication.clipboard().mimeData()
        img = None
        if md is not None and md.hasImage():
            img = QImage(md.imageData())
        elif md is not None and md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    return self.open_path(url.toLocalFile())
        if img is None or img.isNull():
            QMessageBox.information(self, APP_NAME, "There's no picture on the clipboard. Copy a picture first.")
            return False
        try:
            self.set_image(image.to_rgba(img), None)
        except image.ImageError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return False
        return True

    def set_image(self, img, path):
        self.img = img
        self.source_path = path
        self.save_path = None
        self.result = None
        self.preview = None
        self.view.set_picture(img.width(), img.height())
        self.view.fit(self.left.size())
        self.left.set_message("")
        self.left.set_picture(img)
        self.right.set_svg("")
        self.right.set_message("")
        self._update_title()
        self._update_actions()
        self.start_trace(auto=self.a_auto_new.isChecked())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        for url in md.urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
                return
        if md.hasImage():
            img = QImage(md.imageData())
            if not img.isNull():
                self.set_image(image.to_rgba(img), None)

    # tracing

    def settings_changed(self):
        self.settings.save(self.qs)
        if self.a_auto.isChecked():
            self.timer.start()

    def auto_changed(self, on):
        self.qs.setValue("trace/auto", int(on))
        if on:
            self.timer.start()

    def auto_settings(self):
        self.start_trace(auto=True)

    def auto_new_changed(self, on):
        self.qs.setValue("trace/auto_new", int(on))

    def start_trace(self, auto=False):
        if self.img is None or self.closing:
            return
        self.timer.stop()
        if self.worker is not None:
            # stop the one running; this one starts when it has
            self.job.cancelled = True
            self.pending = True
            self.pending_auto = self.pending_auto or auto
            return
        auto = auto or self.pending_auto
        self.pending = False
        self.pending_auto = False
        self.job_number += 1
        self.job = Job(self.job_number, self.img, self.settings.options(), self.settings.enlarge_setting(),
                       self.a_colors.isChecked(), auto)
        self.worker = Worker(self.job)
        self.worker.progress.connect(self.on_progress)
        self.worker.auto_done.connect(self.on_auto_done)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_finished)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText("Picking settings..." if auto else "Tracing...")
        self.worker.start()

    def on_auto_done(self, number, options, info):
        if number != self.job_number or self.job.cancelled:
            return
        self.settings.apply_auto(options)
        self.settings.save(self.qs)
        self.status.setText(describe_auto(options, info) + ". Tracing...")

    def on_progress(self, number, f):
        if number == self.job_number:
            self.bar.setValue(int(f * 1000))

    def on_done(self, number, result, preview):
        if number != self.job_number or self.job.cancelled:
            return
        self.result = result
        if preview is not None:
            self.preview = preview
        self.right.set_message("")
        self.right.set_svg(result.svg)
        if self.a_colors.isChecked() and self.preview is not None:
            self.left.set_picture(self.preview)
        size = len(result.svg.encode("utf-8"))
        text = "%d shapes, %s, traced in %.2f s" % (result.shapes, _size_text(size), result.seconds)
        if result.factor != 1:
            text += " (at %d times the size)" % result.factor
        if self.job.auto_info is not None:
            text = describe_auto(self.job.options, self.job.auto_info) + ". " + text[0].upper() + text[1:]
        self.status.setText(text)
        self._update_actions()

    def on_failed(self, number, message):
        if number != self.job_number or not message:
            return
        self.result = None
        self.right.set_svg("")
        self.right.set_message("Couldn't trace the picture:\n" + message)
        self.status.setText("")
        self._update_actions()

    def on_finished(self):
        w = self.worker
        self.worker = None
        if w is not None:
            w.deleteLater()
        self.bar.hide()
        if self.pending:
            self.start_trace()

    def show_colors_changed(self, on):
        if self.img is None:
            return
        if on:
            if self.preview is None:
                self.start_trace()
            else:
                self.left.set_picture(self.preview)
        else:
            self.left.set_picture(self.img)
        self.left.title = "Colors to trace" if on else "Picture"
        self.left.update()

    def actual_size(self):
        self.view.scale = 1.0
        self.view.fitted = False
        self.view.changed.emit()

    # saving

    def default_name(self):
        if self.source_path:
            return os.path.splitext(self.source_path)[0] + ".svg"
        return os.path.join(self.qs.value("paths/save", os.path.expanduser("~")), "picture.svg")

    def save(self):
        if self.save_path:
            return self.write(self.save_path)
        return self.save_as()

    def save_as(self):
        if self.result is None:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save SVG", self.save_path or self.default_name(),
                                              "SVG files (*.svg)")
        if not path:
            return False
        if not path.lower().endswith(".svg"):
            path += ".svg"
        return self.write(path)

    def write(self, path):
        if self.result is None:
            return False
        tmp = path + ".part"
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.result.svg)
            os.replace(tmp, path)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            QMessageBox.warning(self, APP_NAME, "Couldn't save %s:\n%s" % (path, e))
            return False
        self.save_path = path
        self.qs.setValue("paths/save", os.path.dirname(path))
        self.status.setText("Saved %s" % path)
        return True

    def copy_svg(self):
        if self.result is None:
            return
        md = QMimeData()
        data = QByteArray(self.result.svg.encode("utf-8"))
        md.setData("image/svg+xml", data)
        md.setText(self.result.svg)
        QGuiApplication.clipboard().setMimeData(md)
        self.status.setText("SVG copied: paste it into Inkscape, Illustrator or another program.")

    # help

    def show_help(self):
        d = QDialog(self)
        d.setWindowTitle("How to use KanzonasSVG")
        lay = QVBoxLayout(d)
        t = QTextBrowser()
        t.setHtml(HELP_HTML)
        lay.addWidget(t)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        b.rejected.connect(d.reject)
        lay.addWidget(b)
        d.resize(640, 700)
        d.exec()

    def about(self):
        try:
            ev = engine.version()
        except engine.TraceError:
            ev = "not found"
        QMessageBox.about(
            self, "About KanzonasSVG",
            "<h3>KanzonasSVG %s</h3>"
            "<p>Turns pictures into SVG files.</p>"
            "<p>Tracing engine %s: Inkscape's Trace Bitmap, with Potrace 1.16 (Peter Selinger) and "
            "Autotrace 0.40 (Martin Weber and others), with quality and speed fixes. Window: Qt for "
            "Python (PySide6).</p>"
            "<p>Free software under the GNU General Public License, version 2 or later. Source code: "
            "<a href='https://github.com/keithlyding/KanzonasSVG'>github.com/keithlyding/KanzonasSVG</a></p>"
            % (__version__, ev))

    def closeEvent(self, e):
        self.closing = True
        self.timer.stop()
        self.pending = False
        self.qs.setValue("window/geometry", self.saveGeometry())
        self.settings.save(self.qs)
        if self.worker is not None:
            self.job.cancelled = True
            self.worker.wait()
        super().closeEvent(e)


def _size_text(n):
    if n < 1024:
        return "%d bytes" % n
    if n < 1024 * 1024:
        return "%.0f KB" % (n / 1024)
    return "%.1f MB" % (n / 1024 / 1024)


def run(argv):
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Kanzonas")
    app.setApplicationVersion(__version__)
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    try:
        engine.library()
    except engine.TraceError as e:
        QMessageBox.critical(None, APP_NAME, str(e))
        return 1
    w = MainWindow()
    w.show()
    for a in argv:
        if not a.startswith("-") and os.path.isfile(a):
            w.open_path(a)
            break
    return app.exec()
