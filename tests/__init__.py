"""Tests. Run: QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t ."""

import atexit
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["KANZONASSVG_LANG"] = "en"   # (the tests read the window's English; tests/test_i18n.py checks Spanish)

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication(["kanzonassvg-tests"])
APP.setOrganizationName("Kanzonas")
APP.setApplicationName("KanzonasSVG-tests")


@atexit.register
def _quit():
    # tear Qt down in order (a QApplication left to the garbage collector can crash at exit).
    # Windows and dialogs a test left (closed but not deleted) go first, while Qt is whole: left
    # to the garbage collector after it, they crashed the process now and then after "OK"
    # (1.3's first build: a segmentation fault on Linux, and on Windows the same run).
    global APP
    from PySide6.QtCore import QEvent
    for w in APP.topLevelWidgets():
        w.close()
        w.deleteLater()
    APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    APP.processEvents()
    APP = None
