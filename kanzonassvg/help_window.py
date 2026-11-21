"""Help > How to use KanzonasSVG (F1): the help in numbered chapters, a list of them to jump
to, and a search that marks every match and says which chapters have them. It doesn't block
the program: keep it open while you work."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, \
    QListWidgetItem, QPushButton, QSplitter, QTextBrowser, QTextEdit, QVBoxLayout

_H3 = re.compile(r"<h3>(.*?)</h3>", re.S)


def chapters(html):
    """(the help with each chapter numbered, marked and set apart, [chapter titles])."""
    titles = []

    def number(m):
        titles.append(re.sub(r"<[^>]+>", "", m.group(1)).strip())
        k = len(titles)
        rule = "<hr>" if k > 1 else ""
        return '%s<a name="ch%d"></a><h3>%d. %s</h3>' % (rule, k, k, m.group(1))
    return _H3.sub(number, html), titles


class HelpWindow(QDialog):
    def __init__(self, parent, html, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(900, 720)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the help (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.found = QLabel()
        self.b_prev = QPushButton("Previous")
        self.b_next = QPushButton("Next")
        top.addWidget(self.search, 1)
        top.addWidget(self.found)
        top.addWidget(self.b_prev)
        top.addWidget(self.b_next)
        lay.addLayout(top)

        split = QSplitter()
        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        split.addWidget(self.list)
        split.addWidget(self.text)
        split.setStretchFactor(1, 1)
        split.setSizes([230, 670])
        lay.addWidget(split, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        lay.addWidget(buttons)

        marked, self.titles = chapters(html)
        self.text.setHtml(marked)
        # where each chapter starts in the text (its numbered heading)
        doc = self.text.document()
        self.starts = []
        at = 0
        for k, t in enumerate(self.titles, 1):
            c = doc.find("%d. %s" % (k, t), at)
            self.starts.append(c.selectionStart() if not c.isNull() else at)
            at = self.starts[-1]
        for k, t in enumerate(self.titles, 1):
            self.list.addItem(QListWidgetItem("%d. %s" % (k, t)))
        self.matches = []          # QTextCursors of the matches
        self.current = -1

        self.list.itemClicked.connect(lambda item: self.go_to_chapter(self.list.row(item)))
        self.list.currentRowChanged.connect(self._row_chosen)
        self.search.textChanged.connect(self.find)
        self.search.returnPressed.connect(self.next_match)
        self.b_next.clicked.connect(self.next_match)
        self.b_prev.clicked.connect(self.previous_match)
        self.text.verticalScrollBar().valueChanged.connect(self._follow)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self.focus_search)
        QShortcut(QKeySequence.StandardKey.FindNext, self, activated=self.next_match)
        QShortcut(QKeySequence.StandardKey.FindPrevious, self, activated=self.previous_match)
        QShortcut(QKeySequence("Shift+Return"), self.search, activated=self.previous_match)
        self._following = False
        self.find("")
        self.list.setCurrentRow(0)

    # chapters

    def go_to_chapter(self, row):
        if 0 <= row < len(self.titles):
            self.text.scrollToAnchor("ch%d" % (row + 1))

    def _row_chosen(self, row):
        if not self._following:
            self.go_to_chapter(row)

    def chapter_at(self, pos):
        k = 0
        for i, s in enumerate(self.starts):
            if s <= pos:
                k = i
        return k

    def _follow(self):
        """The chapter at the top of the text, selected in the list (as you scroll)."""
        bar = self.text.verticalScrollBar()
        # (scrolled to the end: the last chapters are short and all in sight; the last one)
        corner = self.text.viewport().rect().bottomLeft() if bar.value() >= bar.maximum() > 0 \
            else self.text.viewport().rect().topLeft()
        pos = self.text.cursorForPosition(corner).position()
        self._following = True
        self.list.setCurrentRow(self.chapter_at(pos))
        self._following = False

    # searching

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def find(self, text):
        """Mark every match of text (case doesn't matter), count them in each chapter, and go
        to the first one."""
        text = text.strip()
        self.matches = []
        doc = self.text.document()
        if text:
            c = doc.find(text, 0)
            while not c.isNull():
                self.matches.append(c)
                c = doc.find(text, c)
        counts = [0] * len(self.titles)
        for m in self.matches:
            counts[self.chapter_at(m.selectionStart())] += 1
        for k, t in enumerate(self.titles):
            item = self.list.item(k)
            item.setText("%d. %s%s" % (k + 1, t, "  (%d)" % counts[k] if counts[k] else ""))
            f = item.font()
            f.setBold(bool(text) and counts[k] > 0)
            item.setFont(f)
            item.setForeground(self.palette().text() if not text or counts[k]
                               else self.palette().placeholderText())
        self.b_next.setEnabled(len(self.matches) > 0)
        self.b_prev.setEnabled(len(self.matches) > 0)
        if not text:
            self.found.setText("")
        elif not self.matches:
            self.found.setText("No matches")
        self.current = -1
        if self.matches:
            self.next_match()
        else:
            self._mark()

    def next_match(self):
        if self.matches:
            self.current = (self.current + 1) % len(self.matches)
            self._show_current()

    def previous_match(self):
        if self.matches:
            self.current = (self.current - 1) % len(self.matches)
            self._show_current()

    def _show_current(self):
        self.found.setText("%d of %d" % (self.current + 1, len(self.matches)))
        c = QTextCursor(self.matches[self.current])
        self.text.setTextCursor(c)
        # a third of the way down, with what comes before it in sight (not at the very edge)
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.value() + self.text.cursorRect(c).top() - self.text.viewport().height() // 3)
        self._mark()

    def _mark(self):
        marks = []
        for i, m in enumerate(self.matches):
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 150, 50) if i == self.current else QColor(255, 236, 120))
            fmt.setForeground(QColor(0, 0, 0))
            sel.format = fmt
            sel.cursor = m
            marks.append(sel)
        self.text.setExtraSelections(marks)

    def keyPressEvent(self, e):
        # Esc: clear the search first, then close
        if e.key() == Qt.Key.Key_Escape and self.search.text():
            self.search.clear()
            return
        super().keyPressEvent(e)
