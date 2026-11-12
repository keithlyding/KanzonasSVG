"""Tests. Run: QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t ."""

import atexit
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication(["kanzonassvg-tests"])
APP.setOrganizationName("Kanzonas")
APP.setApplicationName("KanzonasSVG-tests")


@atexit.register
def _quit():
    # tear Qt down in order (a QApplication left to the garbage collector can crash at exit)
    global APP
    APP.processEvents()
    APP = None
