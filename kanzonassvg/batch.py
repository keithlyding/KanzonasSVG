"""Many pictures at once (File > Convert many pictures...): each picture traced, with Auto
settings for each or with the settings shown, and saved as SVG, PDF, EPS or DXF at the Saved
width, next to it or in one folder. The work runs in the background, one picture at a time
(the engine already uses every core for each), and can be stopped between pictures or during
one."""

import os

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, \
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton, \
    QRadioButton, QVBoxLayout

from kanzonassvg import engine, export, i18n, image, tracing
from kanzonassvg.i18n import tr

NEXT_TO_EACH = ""        # (the folder setting: next to each picture)


def picked_options(img, snap=0):
    """The settings Auto picks for img (with Snap shapes as given: Auto leaves it as it is),
    and Enlarge first (tracing.AUTO or a factor)."""
    from dataclasses import replace
    picked, info = engine.auto(*image.pixels(img))
    return replace(picked, snap=snap), info.enlarge or tracing.AUTO


def output_path(src, folder, fmt):
    name = os.path.splitext(os.path.basename(src))[0] + "." + fmt
    return os.path.join(folder or os.path.dirname(os.path.abspath(src)), name)


def convert(src, dst, fmt, size, options=None, enlarge=tracing.AUTO, progress=None, snap=0):
    """Trace the picture src (options None: Auto settings for it, with <snap>) and save it to
    dst. Returns the tracing.Result."""
    img = image.load(src)
    if options is None:
        options, enlarge = picked_options(img, snap)
    res = tracing.trace_image(img, options, enlarge, progress)
    export.write(dst, res.svg, fmt, size)
    return res


def picture_files(folder):
    """The pictures in folder (not in folders inside it), sorted by name; not SVGs (they're
    vector already, and the folder may hold the SVGs made from its pictures)."""
    exts = tuple("." + e for e in image.supported_suffixes() if e not in ("svg", "svgz"))
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if n.lower().endswith(exts) and os.path.isfile(os.path.join(folder, n))]


class BatchWorker(QThread):
    """Converts the pictures one by one; item_done(row, ok, text) after each."""

    started_item = Signal(int)
    item_done = Signal(int, bool, str)

    def __init__(self, files, folder, fmt, size, options, enlarge, replace, snap=0):
        super().__init__()
        self.files, self.folder, self.fmt, self.size = files, folder, fmt, size
        self.options, self.enlarge, self.replace, self.snap = options, enlarge, replace, snap
        self.cancelled = False

    def run(self):
        for row, src in enumerate(self.files):
            if self.cancelled:
                return
            self.started_item.emit(row)
            dst = output_path(src, self.folder, self.fmt)
            if os.path.exists(dst) and not self.replace:
                self.item_done.emit(row, False, tr("skipped: %s is already there") % os.path.basename(dst))
                continue
            try:
                res = convert(src, dst, self.fmt, self.size, self.options, self.enlarge,
                              lambda _f: self.cancelled, self.snap)
                self.item_done.emit(row, True, tr("saved %s: %d shapes, %s nodes") % (
                    os.path.basename(dst), res.shapes, i18n.whole(res.nodes)))
            except engine.Cancelled:
                self.item_done.emit(row, False, tr("stopped"))
                return
            except Exception as e:      # (a picture that can't be read or saved: said, and on to the next)
                self.item_done.emit(row, False, tr("failed: %s") % (str(e) or e.__class__.__name__))


class BatchDialog(QDialog):
    """The list of pictures, how to trace and save them, and their progress."""

    def __init__(self, window, files=()):
        super().__init__(window)
        self.window = window
        self.qs = window.qs
        self.worker = None
        self.results = {}           # row: (ok, text)
        self.setWindowTitle(tr("Convert many pictures"))
        self.resize(720, 560)
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(tr("Pictures (drag more in, or add them):")))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.b_add = QPushButton(tr("Add pictures..."))
        self.b_folder = QPushButton(tr("Add a folder..."))
        self.b_remove = QPushButton(tr("Remove"))
        self.b_clear = QPushButton(tr("Clear"))
        for b in (self.b_add, self.b_folder, self.b_remove, self.b_clear):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        form = QFormLayout()
        self.r_auto = QRadioButton(tr("Auto settings for each picture"))
        self.r_shown = QRadioButton(tr("The settings shown now (the same for all; not the color edits)"))
        self.r_auto.setChecked(int(self.qs.value("batch/auto", 1)) != 0)
        self.r_shown.setChecked(not self.r_auto.isChecked())
        group = QButtonGroup(self)
        group.addButton(self.r_auto)
        group.addButton(self.r_shown)
        how = QVBoxLayout()
        how.addWidget(self.r_auto)
        how.addWidget(self.r_shown)
        form.addRow(tr("Settings"), how)
        self.format = QComboBox()
        for f in export.FORMATS:
            self.format.addItem(export.filter_text(f), f)
        last = self.qs.value("batch/format", self.qs.value("paths/format", "svg"))
        self.format.setCurrentIndex(max(0, self.format.findData(last)))
        form.addRow(tr("Save as"), self.format)
        self.size_label = QLabel()
        form.addRow(tr("Width"), self.size_label)
        where = QHBoxLayout()
        self.where = QComboBox()
        self.where.addItem(tr("Next to each picture"), NEXT_TO_EACH)
        self.where.addItem(tr("In this folder:"), "folder")
        self.folder = QLineEdit(self.qs.value("batch/folder", ""))
        self.b_browse = QPushButton(tr("Browse..."))
        where.addWidget(self.where)
        where.addWidget(self.folder, 1)
        where.addWidget(self.b_browse)
        self.where.setCurrentIndex(1 if self.qs.value("batch/where", "") == "folder" else 0)
        form.addRow(tr("Save to"), where)
        self.replace = QCheckBox(tr("Replace files that are already there"))
        form.addRow("", self.replace)
        lay.addLayout(form)

        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        self.b_open = QPushButton(tr("Open the folder"))
        self.b_start = QPushButton(tr("Convert"))
        self.b_start.setDefault(True)
        self.b_stop = QPushButton(tr("Stop"))
        self.b_close = QPushButton(tr("Close"))
        row.addWidget(self.b_open)
        row.addStretch(1)
        for b in (self.b_start, self.b_stop, self.b_close):
            row.addWidget(b)
        lay.addLayout(row)

        self.b_add.clicked.connect(self.add_dialog)
        self.b_folder.clicked.connect(self.add_folder_dialog)
        self.b_remove.clicked.connect(self.remove_selected)
        self.b_clear.clicked.connect(self.clear)
        self.b_browse.clicked.connect(self.browse)
        self.where.currentIndexChanged.connect(self._update)
        self.b_start.clicked.connect(self.start)
        self.b_stop.clicked.connect(self.stop)
        self.b_close.clicked.connect(self.close)
        self.b_open.clicked.connect(self.open_folder)
        self.add_files(files)
        self._update()

    # the list

    def files(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def add_files(self, paths):
        have = set(self.files())
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isdir(p):
                self.add_files(picture_files(p))
                continue
            if p in have or not os.path.isfile(p):
                continue
            have.add(p)
            item = QListWidgetItem(p)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.list.addItem(item)
        self._list_changed()

    def add_dialog(self):
        from kanzonassvg.app import picture_filter
        start = self.qs.value("paths/open", os.path.expanduser("~"))
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Add pictures"), start, picture_filter())
        if paths:
            self.qs.setValue("paths/open", os.path.dirname(paths[0]))
            self.add_files(paths)

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Add the pictures in a folder"),
                                                  self.qs.value("paths/open", os.path.expanduser("~")))
        if folder:
            self.add_files([folder])

    def remove_selected(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))
        self._list_changed()

    def clear(self):
        self.list.clear()
        self._list_changed()

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Save the files in"), self.folder.text()
                                                  or os.path.expanduser("~"))
        if folder:
            self.folder.setText(folder)
            self.where.setCurrentIndex(1)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self.worker is None:
            self.add_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    # doing it

    def target_folder(self):
        return self.folder.text().strip() if self.where.currentData() == "folder" else NEXT_TO_EACH

    def _update(self):
        busy = self.worker is not None
        n = self.list.count()
        self.b_start.setEnabled(not busy and n > 0)
        self.b_stop.setEnabled(busy)
        self.b_close.setEnabled(not busy)
        for w in (self.b_add, self.b_folder, self.b_remove, self.b_clear, self.r_auto, self.r_shown, self.format,
                  self.where, self.replace):
            w.setEnabled(not busy)
        in_folder = self.where.currentData() == "folder"
        self.folder.setEnabled(in_folder and not busy)
        self.b_browse.setEnabled(not busy)
        self.b_open.setEnabled(bool(self.results) and (not in_folder or os.path.isdir(self.target_folder())))
        size = self.window.settings.saved_size()
        if size.unit == export.PX:
            self.size_label.setText(tr("Each picture's own size in pixels (96 to the inch): set Saved width "
                                    "under Size to save them at a width"))
        else:
            self.size_label.setText(tr("%s %s wide (Saved width, under Size), the height following each picture")
                                    % (("%.2f" % size.width).rstrip("0").rstrip("."), size.unit))

    def _list_changed(self):
        """The list changed: the last run's results and summary go."""
        n = self.list.count()
        self.results.clear()
        self._show_results()
        self.bar.setRange(0, max(1, n))
        self.bar.setValue(0)
        self.summary.setText(tr("No pictures yet.") if not n else tr("1 picture") if n == 1 else tr("%d pictures") % n)
        self._update()

    def start(self):
        files = self.files()
        if not files or self.worker is not None:
            return
        folder = self.target_folder()
        if self.where.currentData() == "folder":
            if not folder:
                self.summary.setText(tr("Choose the folder to save them in (Browse...)."))
                return
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                self.summary.setText(tr("Can't use that folder: %s") % e)
                return
        fmt = self.format.currentData()
        if self.r_auto.isChecked():
            options, enlarge = None, tracing.AUTO
        else:
            from dataclasses import replace
            options = replace(self.window.settings.options(), edits=())
            enlarge = self.window.settings.enlarge_setting()
        self.qs.setValue("batch/auto", int(self.r_auto.isChecked()))
        self.qs.setValue("batch/format", fmt)
        self.qs.setValue("batch/where", self.where.currentData())
        self.qs.setValue("batch/folder", self.folder.text())
        self.results.clear()
        self._show_results()
        self.bar.setRange(0, len(files))
        self.bar.setValue(0)
        self.worker = BatchWorker(files, folder, fmt, self.window.settings.saved_size(), options, enlarge,
                                  self.replace.isChecked(), self.window.settings.options().snap)
        self.worker.started_item.connect(self._started_item)
        self.worker.item_done.connect(self._item_done)
        self.worker.finished.connect(self._finished)
        self._update()
        self.worker.start()

    def stop(self):
        if self.worker is not None:
            self.worker.cancelled = True
            self.summary.setText(tr("Stopping..."))

    def _started_item(self, row):
        self.list.setCurrentRow(row)
        self.summary.setText(tr("Converting %d of %d: %s") % (row + 1, self.list.count(),
                                                          os.path.basename(self.files()[row])))

    def _item_done(self, row, ok, text):
        self.results[row] = (ok, text)
        self.bar.setValue(len(self.results))
        self._show_results()

    def _show_results(self):
        for i in range(self.list.count()):
            item = self.list.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            if i in self.results:
                ok, text = self.results[i]
                item.setText("%s  -  %s" % (path, text))
                item.setForeground(self.palette().text() if ok else Qt.GlobalColor.darkRed)
            else:
                item.setText(path)
                item.setForeground(self.palette().text())

    def _finished(self):
        w, self.worker = self.worker, None
        w.wait()
        saved = sum(1 for ok, _t in self.results.values() if ok)
        others = len(self.results) - saved
        text = tr("Saved %d of %d") % (saved, self.list.count())
        if others:
            text += tr("; %d not (see the list)") % others
        if w.cancelled:
            text += tr("; stopped")
        self.summary.setText(text + ".")
        self._update()

    def open_folder(self):
        folder = self.target_folder()
        if not folder:
            rows = [r for r, (ok, _t) in self.results.items() if ok]
            if not rows:
                return
            folder = os.path.dirname(self.files()[rows[0]])
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def wait(self):
        """Wait for the work to end (for closing, and the tests)."""
        while self.worker is not None:
            self.worker.wait(50)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()

    def closeEvent(self, e):
        if self.worker is not None:
            self.worker.cancelled = True
            self.wait()
        super().closeEvent(e)

    def reject(self):           # (Esc: as Close, stopping first)
        self.close()
