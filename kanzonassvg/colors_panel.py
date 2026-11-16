"""The Colors panel: the colors a trace uses, to change, merge or leave out before tracing.

The edits are kept as (original color, new color or None, where) and handed to the engine with
the other settings (engine.Options.edits): each traced color takes the edit whose original is
nearest (within engine.EDIT_MATCH levels), so they still apply when the colors are picked again
(another number of colors, Smooth, a crop) and a color comes back a level or two off. The
background (the background color's area reaching the edge, or the transparent part) is a swatch
of its own, so that color inside the picture is edited apart from it (engine.BACKGROUND,
engine.INSIDE). They're for the picture shown: a new picture starts without them.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QColorDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMenu, \
    QPushButton, QToolButton, QVBoxLayout, QWidget

from kanzonassvg import engine

COLUMNS = 6
SWATCH = 30
# the background color's areas inside the picture get a swatch of their own unless they're this
# small a part of it (stray pixels: they go with the background's swatch, and its edits)
TINY_INSIDE = 0.0005
# selected swatches: a thick frame in the highlight color
SWATCH_STYLE = ("QToolButton { border: 3px solid transparent; padding: 0px; } "
                "QToolButton:checked { border: 3px solid palette(highlight); }")


def ctrl_held():
    """Ctrl (on a Mac, Command) is held: a click adds to the selection."""
    return bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)


def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def swatch_icon(rgb, left_out=False, background=False):
    pm = QPixmap(SWATCH, SWATCH)
    p = QPainter(pm)
    if left_out:
        # see-through: a checkerboard, crossed out
        for y in range(0, SWATCH, 6):
            for x in range(0, SWATCH, 6):
                p.fillRect(x, y, 6, 6, QColor(205, 205, 205) if (x + y) // 6 % 2 else QColor(255, 255, 255))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(200, 30, 30), 3))
        p.drawLine(4, SWATCH - 4, SWATCH - 4, 4)
    else:
        p.fillRect(0, 0, SWATCH, SWATCH, QColor(*rgb))
    if background:
        # the background: a dashed frame inside, in a color that shows on it (the area around)
        dark = not left_out and sum(rgb) < 3 * 128
        p.setPen(QPen(QColor(255, 255, 255) if dark else QColor(60, 60, 60), 2, Qt.PenStyle.DashLine))
        p.drawRect(6, 6, SWATCH - 13, SWATCH - 13)
    p.setPen(QColor(120, 120, 120))
    p.drawRect(0, 0, SWATCH - 1, SWATCH - 1)
    p.end()
    return QIcon(pm)


class Group:
    """One swatch: palette colors traced as one color (merged, or alone), or one left out."""

    def __init__(self, color, left_out, background=False):
        self.color = color          # what it's traced as (its own color if not edited)
        self.left_out = left_out
        self.background = background
        self.members = []           # (original color, engine.INSIDE or engine.BACKGROUND)
        self.count = 0              # pixels


class ColorsPanel(QGroupBox):
    """changed: the edits changed (trace again)."""

    changed = Signal()

    def __init__(self):
        super().__init__("Colors")
        self.palette = []           # [((r, g, b), pixels, is_background)] of the last trace, before edits
        self.edits = []             # [((r, g, b), (r, g, b) or None, where)]
        self.groups = []
        self.buttons = []
        self.selected = set()       # the selected swatches' members: (original color, where)
        lay = QVBoxLayout(self)
        self.hint = QLabel("Click a color to select it, Ctrl+click to select more (here, on the picture "
                           "or on the SVG), then change, merge or leave them out.")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.grid_box = QWidget()
        self.grid = QGridLayout(self.grid_box)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(3)
        lay.addWidget(self.grid_box)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.hide()
        lay.addWidget(self.note)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        self.b_change = QPushButton("Change color...")
        self.b_change.setToolTip("Trace the selected colors as another color")
        self.b_merge = QPushButton("Merge")
        self.b_merge.setToolTip("Trace the selected colors as one color, picked from them (or another)")
        self.b_out = QPushButton("Leave out")
        self.b_out.setToolTip("Leave the selected colors out: the SVG is see-through there (again: put them back)")
        self.b_reset = QPushButton("Reset colors")
        self.b_reset.setToolTip("Undo the edits of the selected colors (none selected: of all)")
        row1.addWidget(self.b_change)
        row1.addWidget(self.b_merge)
        row2.addWidget(self.b_out)
        row2.addWidget(self.b_reset)
        lay.addLayout(row1)
        lay.addLayout(row2)
        self.b_change.clicked.connect(lambda: self.change_color())     # (not clicked's checked flag)
        self.b_merge.clicked.connect(lambda: self.merge())               # (not clicked's checked flag)
        self.b_out.clicked.connect(self.leave_out)
        self.b_reset.clicked.connect(self.reset)
        self._rebuild()

    # what the trace gets

    def edits_tuple(self):
        return tuple(self.edits)

    def edited_count(self):
        """How many of the traced colors an edit changes or leaves out."""
        n = 0
        for color, where in self.entries():
            e = engine.edit_for(color, self.edits, where)
            if e is not None and (e[1] is None or tuple(e[1]) != tuple(color)):
                n += 1
        return n

    def entries(self):
        """The colors traced: [(color, where)] (the background's where: engine.BACKGROUND)."""
        return [(tuple(c), engine.BACKGROUND if bg else engine.INSIDE) for c, n, bg in self.palette if n > 0]

    def total(self):
        return sum(n for _c, n, _bg in self.palette) or 1

    def clear(self):
        """A new picture: no edits, no colors yet."""
        changed = bool(self.edits)
        self.edits, self.palette, self.selected = [], [], set()
        self._rebuild()
        return changed

    def set_palette(self, palette):
        """The colors the last trace used (engine.palette)."""
        self.palette = [(tuple(c), n, bool(bg)) for c, n, bg in (palette or [])]
        self._rebuild()

    # the swatches

    def _groups(self):
        """The swatches: colors traced as one (merged, or alone), the background always its own,
        each left out alone."""
        groups, by_color = [], {}
        total = self.total()
        bg_color = next((tuple(c) for c, n, bg in self.palette if bg and n > 0), None)
        tiny = None                 # (the background color's few pixels inside, if that's all)
        for color, count, bg in self.palette:
            if not bg and bg_color == tuple(color) and 0 < count < TINY_INSIDE * total:
                tiny = (tuple(color), count)
        for color, count, bg in self.palette:
            if count <= 0 or (tiny is not None and not bg and tuple(color) == tiny[0]):
                continue
            where = engine.BACKGROUND if bg else engine.INSIDE
            e = engine.edit_for(color, self.edits, where)
            left_out = e is not None and e[1] is None
            final = tuple(color) if e is None else tuple(e[1] or color)
            if left_out or bg:
                g = Group(final, left_out, bg)
                groups.append(g)
            else:
                g = by_color.get(final)
                if g is None:
                    g = by_color[final] = Group(final, False)
                    groups.append(g)
            g.members.append((tuple(color), where))
            g.count += count
            if bg and tiny is not None:
                g.members.append((tiny[0], engine.INSIDE))      # (edited with it)
                g.count += tiny[1]
        return groups

    def _rebuild(self):
        for b in self.buttons:
            # gone now (deleteLater alone left it shown until the event loop got to it)
            self.grid.removeWidget(b)
            b.hide()
            b.setParent(None)
            b.deleteLater()
        self.buttons = []
        self.groups = self._groups()
        total = self.total()
        present = {m for g in self.groups for m in g.members}
        self.selected &= present
        for i, g in enumerate(self.groups):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(swatch_icon(g.color, g.left_out, g.background))
            b.setIconSize(QSize(SWATCH, SWATCH))
            b.setAutoRaise(False)
            b.setStyleSheet(SWATCH_STYLE)
            b.setChecked(bool(set(g.members) & self.selected))
            share = 100.0 * g.count / total
            first = g.members[0][0]
            if g.left_out:
                tip = "%s, left out (%.1f%% of the picture)" % (hex_of(first), share)
            elif len(g.members) > 1:
                tip = "%s: %d colors merged (%s), %.1f%% of the picture" % (
                    hex_of(g.color), len(g.members), ", ".join(hex_of(m) for m, _w in g.members), share)
            elif first != g.color:
                tip = "%s, traced as %s (%.1f%% of the picture)" % (hex_of(first), hex_of(g.color), share)
            else:
                tip = "%s (%.1f%% of the picture)" % (hex_of(g.color), share)
            if g.background:
                tip = "The background: " + tip + ". The same color inside the picture is a swatch of its own."
            b.setToolTip(tip)
            b.clicked.connect(lambda _checked=False, g=g: self.click_group(g, ctrl_held()))
            self.grid.addWidget(b, i // COLUMNS, i % COLUMNS)
            self.buttons.append(b)
        # edits that apply to no color now (the colors were picked again): kept, they apply again
        # if a matching color comes back
        used = {id(engine.edit_for(c, self.edits, w)) for c, w in self.entries()}
        unused = [e for e in self.edits if id(e) not in used]
        if unused and self.entries():
            self.note.setText("%d color edit%s match%s no color now (they apply again if the color comes "
                              "back; Reset colors clears them)." % (
                                  len(unused), "" if len(unused) == 1 else "s", "es" if len(unused) == 1 else ""))
            self.note.show()
        else:
            self.note.hide()
        self._update_buttons()

    def click_group(self, g, add=False):
        """A click on a swatch (or on the picture or the SVG where it's traced): select just it,
        or with Ctrl held (add) add it to the selection, or take it out if it's in it."""
        members = set(g.members)
        if add:
            if members & self.selected:
                self.selected -= members
            else:
                self.selected |= members
        else:
            self.selected = members
        for grp, b in zip(self.groups, self.buttons):
            b.blockSignals(True)
            b.setChecked(bool(set(grp.members) & self.selected))
            b.blockSignals(False)
        self._update_buttons()

    def _selected_groups(self):
        return [g for g in self.groups if set(g.members) & self.selected]

    def _update_buttons(self):
        sel = self._selected_groups()
        kept = [g for g in sel if not g.left_out]
        self.b_change.setEnabled(bool(kept))
        self.b_merge.setEnabled(len(kept) >= 2)
        self.b_out.setEnabled(bool(sel))
        self.b_out.setText("Put back" if sel and all(g.left_out for g in sel) else "Leave out")
        self.b_reset.setEnabled(bool(self.edits))

    def select_at(self, color, add=False, background=False):
        """Select the swatch of the traced color nearest to <color> (a picture's pixel; in the
        background or not) as a click on it does (add: Ctrl held). Returns its group."""
        if background:
            g = next((g for g in self.groups if g.background), None)
            if g is not None:
                self.click_group(g, add)
            return g
        inside = [(c, w) for c, w in self.entries() if w == engine.INSIDE]
        if not inside:
            return None
        nearest = min(inside, key=lambda m: sum((a - b) ** 2 for a, b in zip(m[0], color)))
        for g in self.groups:
            if nearest in g.members:
                self.click_group(g, add)
                return g
        return None

    # for Undo: the edits as they are, and put back

    def state(self):
        return tuple(self.edits)

    def set_state(self, edits):
        self.edits = list(edits)
        self._rebuild()

    # the edits

    def _set(self, member, to):
        """member ((original color, where)) is traced as <to> (None: left out)."""
        color, where = member
        self.edits = [e for e in self.edits if not (tuple(e[0]) == color and engine.edit_where(e) == where)]
        if to is None or tuple(to) != color:
            self.edits.append((color, None if to is None else tuple(to), where))
        elif engine.edit_for(color, self.edits, where) is not None:
            # back to its own color, but an edit made for a color a level or two off (or for
            # everywhere) would still apply: say "its own color" outright
            self.edits.append((color, color, where))

    def _drop(self, member):
        """No edit applies to member any more (also one made for a color a level or two off).
        One for everywhere is split: it stays for the other area."""
        color, where = member
        while True:
            e = engine.edit_for(color, self.edits, where)
            if e is None:
                return
            self.edits.remove(e)
            if engine.edit_where(e) == engine.EVERYWHERE:
                other = engine.BACKGROUND if where == engine.INSIDE else engine.INSIDE
                self.edits.append((tuple(e[0]), e[1], other))

    def _done(self):
        self._rebuild()
        self.changed.emit()

    def change_color(self, color=None):
        kept = [g for g in self._selected_groups() if not g.left_out]
        if not kept:
            return
        if color is None:
            picked = QColorDialog.getColor(QColor(*kept[0].color), self, "Trace the selected colors as")
            if not picked.isValid():
                return
            color = (picked.red(), picked.green(), picked.blue())
        for g in kept:
            for m in g.members:
                self._set(m, color)
        self._done()

    def merge(self, target=None):
        """Trace the selected colors as one: <target>, or the one picked from a list of them
        (or another color)."""
        kept = [g for g in self._selected_groups() if not g.left_out]
        if len(kept) < 2:
            return
        if target is None:
            target = self._pick_merge_color(kept)
            if target is None:
                return
        for g in kept:
            for m in g.members:
                self._set(m, target)
        self._done()

    def _pick_merge_color(self, kept):
        """The list Merge opens: each selected color (biggest first), and Another color..."""
        total = self.total()
        menu = QMenu(self)
        menu.addSection("Merge into")
        for g in sorted(kept, key=lambda g: -g.count):
            a = menu.addAction(swatch_icon(g.color, background=g.background), "%s  (%.1f%%)%s" % (
                hex_of(g.color), 100.0 * g.count / total, "  background" if g.background else ""))
            a.setData(list(g.color))       # (the color on the action: wrappers of it compare unequal)
        menu.addSeparator()
        other = menu.addAction("Another color...")
        other.setData("other")
        chosen = self.open_menu(menu, self.b_merge.mapToGlobal(self.b_merge.rect().bottomLeft()))
        if chosen is None:
            return None
        if chosen.data() == "other":
            picked = QColorDialog.getColor(QColor(*kept[0].color), self, "Merge the selected colors into")
            return (picked.red(), picked.green(), picked.blue()) if picked.isValid() else None
        return tuple(chosen.data())

    def open_menu(self, menu, where):
        """Show menu at where and return the action chosen (None: none). (A test answers it.)"""
        return menu.exec(where)

    def leave_out(self):
        sel = self._selected_groups()
        if not sel:
            return
        if all(g.left_out for g in sel):
            for g in sel:                 # put back
                for m in g.members:
                    self._drop(m)
        else:
            for g in sel:
                for m in g.members:
                    self._set(m, None)
        self._done()

    def reset(self):
        sel = self._selected_groups()
        if sel:
            for g in sel:
                for m in g.members:
                    self._drop(m)
        else:
            self.edits = []
        self._done()

