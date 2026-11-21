"""Help > How to use KanzonasSVG (1.6): numbered chapters, the chapter list, the search."""

import re
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from kanzonassvg import app
from kanzonassvg.help_window import chapters


class TestHelpWindow(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.w = app.MainWindow()
        self.h = self.w.show_help()
        QApplication.processEvents()

    def tearDown(self):
        self.w.close()

    def test_chapters(self):
        html, titles = chapters(app.HELP_HTML)
        expect = re.findall(r"<h3>(.*?)</h3>", app.HELP_HTML)
        self.assertEqual(titles, expect)
        self.assertIn("Saving", titles)
        for k, t in enumerate(titles, 1):
            self.assertIn('<a name="ch%d"></a><h3>%d. %s</h3>' % (k, k, t), html)
        self.assertEqual(html.count("<hr>"), len(titles) - 1)
        self.assertEqual(self.h.list.count(), len(titles))
        self.assertEqual(self.h.list.item(0).text(), "1. " + titles[0])
        # each chapter's place in the text, in order
        self.assertEqual(self.h.starts, sorted(self.h.starts))
        self.assertEqual(len(set(self.h.starts)), len(titles))

    def test_jumping_to_a_chapter_and_following(self):
        row = self.h.titles.index("Saving")
        self.h.list.setCurrentRow(row)
        QApplication.processEvents()
        top = self.h.text.cursorForPosition(self.h.text.viewport().rect().topLeft()).position()
        self.assertEqual(self.h.chapter_at(top), row)
        # scrolling the text selects the chapter there
        self.h.text.verticalScrollBar().setValue(self.h.text.verticalScrollBar().maximum())
        QApplication.processEvents()
        self.assertEqual(self.h.list.currentRow(), len(self.h.titles) - 1)

    def test_search(self):
        h = self.h
        h.search.setText("dxf")                 # (case doesn't matter)
        n = len(h.matches)
        self.assertEqual(n, len(re.findall("dxf", h.text.toPlainText(), re.I)))
        self.assertGreater(n, 2)
        self.assertEqual(h.found.text(), "1 of %d" % n)
        self.assertEqual(len(h.text.extraSelections()), n)
        saving = h.titles.index("Saving")
        self.assertTrue(h.list.item(saving).text().endswith(")"))
        self.assertTrue(h.list.item(saving).font().bold())
        undo = h.titles.index("Undo")
        self.assertFalse(h.list.item(undo).font().bold())
        h.next_match()
        self.assertEqual(h.found.text(), "2 of %d" % n)
        h.previous_match()
        h.previous_match()
        self.assertEqual(h.found.text(), "%d of %d" % (n, n))       # (round to the last)
        self.assertEqual(h.text.textCursor().selectedText().lower(), "dxf")
        # nothing found; then cleared with Esc (a second Esc closes)
        h.search.setText("zzqqxx")
        self.assertEqual(h.found.text(), "No matches")
        self.assertFalse(h.b_next.isEnabled())
        h.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(h.search.text(), "")
        self.assertEqual(h.found.text(), "")
        self.assertEqual(h.text.extraSelections(), [])
        self.assertTrue(h.isVisible())
        self.assertEqual(h.list.item(undo).text(), "%d. Undo" % (undo + 1))

    def test_one_window(self):
        self.assertIs(self.w.show_help(), self.h)
        self.assertFalse(self.h.isModal())      # (the program can be used beside it)


if __name__ == "__main__":
    unittest.main()
