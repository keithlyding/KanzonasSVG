"""The ribbon's icons: glyphs of the Material Design Icons font in kanzonassvg/fonts (as
KanzonasPDF draws its own), drawn sharp at any size and screen scale, in the system's text color
(light or dark), grayed when their button is."""

import os
import sys

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QIconEngine, QPainter, \
    QPalette, QPixmap

FONT = "materialdesignicons6-webfont-6.9.96.ttf"

# the icons used, by name, and their places in the font (from the font's character map,
# materialdesignicons6-webfont-charmap-6.9.96.json in qtawesome 1.4.0: reading all of it took
# 60 ms of the start; tests/test_ribbon.py checks every icon the window names is here)
CODES = {
    "auto-fix": 0xF0068,
    "backup-restore": 0xF006F,
    "content-copy": 0xF018F,
    "content-paste": 0xF0192,
    "content-save-outline": 0xF0818,
    "crop": 0xF019E,
    "crop-free": 0xF019F,
    "cursor-default-click-outline": 0xF0CFE,
    "eraser": 0xF01FE,
    "eye-off-outline": 0xF06D1,
    "file-export-outline": 0xF102E,
    "file-pdf-box": 0xF0226,
    "fit-to-screen-outline": 0xF18F5,
    "folder-open-outline": 0xF0DCF,
    "format-color-fill": 0xF0266,
    "help-circle-outline": 0xF0625,
    "image-filter-center-focus": 0xF02F1,
    "image-multiple-outline": 0xF02EF,
    "information-outline": 0xF02FD,
    "magnify-minus-outline": 0xF06EC,
    "magnify-plus-outline": 0xF06ED,
    "merge": 0xF0F5C,
    "minus-circle-outline": 0xF0377,
    "numeric-1-box-outline": 0xF03A6,
    "palette-outline": 0xF0E0C,
    "plus-circle-outline": 0xF0419,
    "redo": 0xF044E,
    "refresh": 0xF0450,
    "restore": 0xF099B,
    "selection-off": 0xF0777,
    "sync": 0xF04E6,
    "undo": 0xF054C,
    "update": 0xF06B0,
    "vector-curve": 0xF0559,
    "vector-polyline": 0xF0561,
    "vector-square": 0xF0001,
}

_font = {}


def _folder():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "kanzonassvg", "fonts")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def _load():
    """The font's family name (None if it can't be read: the buttons then show their names only)."""
    if not _font:
        _font["family"] = None
        try:
            folder = _folder()
            fid = QFontDatabase.addApplicationFont(os.path.join(folder, FONT))
            families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if families:
                _font["family"] = families[0]
        except OSError:
            _font["family"] = None
    return _font["family"]


class _Glyph(QIconEngine):
    def __init__(self, char):
        super().__init__()
        self.char = char

    def paint(self, painter, rect, mode, state):
        painter.save()
        font = QFont(_font["family"])
        font.setPixelSize(max(1, round(rect.height() * 0.875)))
        painter.setFont(font)
        app = QGuiApplication.instance()
        c = QColor(app.palette().color(QPalette.ColorRole.WindowText)) if app else QColor(48, 48, 48)
        if mode == QIcon.Mode.Disabled:
            c.setAlphaF(0.35)
        painter.setPen(c)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.char)
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(QPoint(0, 0), size), mode, state)
        p.end()
        return pm

    def clone(self):
        return _Glyph(self.char)


def icon(name):
    """The icon of that Material Design Icons name (an empty icon if there is none)."""
    code = CODES.get(name)
    if code and _load():
        return QIcon(_Glyph(chr(code)))
    return QIcon()
