"""The Colors panel: the colors a trace uses, to change, merge or leave out before tracing.

The edits are kept as (original color, new color or None) pairs and handed to the engine with
the other settings (engine.Options.edits): each traced color takes the edit whose original is
nearest (within engine.EDIT_MATCH levels), so they still apply when the colors are picked again
(another number of colors, Smooth, a crop) and a color comes back a level or two off. They're
for the picture shown: a new picture starts without them.
"""

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QColorDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, \
    QToolButton, QVBoxLayout, QWidget

from kanzonassvg import engine

COLUMNS = 6
SWATCH = 30
# selected swatches: a thick frame in the highlight color
SWATCH_STYLE = ("QToolButton { border: 3px solid transparent; padding: 0px; } "
                "QToolButton:checked { border: 3px solid palette(highlight); }")


def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def swatch_icon(rgb, left_out=False):
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
    p.setPen(QColor(120, 120, 120))
    p.drawRect(0, 0, SWATCH - 1, SWATCH - 1)
    p.end()
    return QIcon(pm)


class Group:
    """One swatch: palette colors traced as one color (merged, or alone), or one left out."""

    def __init__(self, color, left_out):
        self.color = color          # what it's traced as (its own color if not edited)
        self.left_out = left_out
        self.members = []           # original colors
        self.count = 0              # pixels


class ColorsPanel(QGroupBox):
    """changed: the edits changed (trace again)."""

    changed = Signal()

    def __init__(self):
        super().__init__("Colors")
        self.palette = []           # [((r, g, b), pixels)] of the last trace, before edits
        self.edits = []             # [((r, g, b), (r, g, b) or None)]
        self.groups = []
        self.buttons = []
        self.selected = set()       # original colors of the selected swatches' members
        lay = QVBoxLayout(self)
        self.hint = QLabel("Click colors to select them (several: click each), then change, merge or "
                           "leave them out. Clicking the picture selects the color there.")
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
        self.b_merge.setToolTip("Trace the selected colors as one: the color of the biggest of them")
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
        self.b_merge.clicked.connect(self.merge)
        self.b_out.clicked.connect(self.leave_out)
        self.b_reset.clicked.connect(self.reset)
        self._rebuild()

    # what the trace gets

    def edits_tuple(self):
        return tuple(self.edits)

    def edited_count(self):
        """How many of the traced colors an edit changes or leaves out."""
        n = 0
        for color, _ in self.palette:
            e = engine.edit_for(color, self.edits)
            if e is not None and (e[1] is None or tuple(e[1]) != tuple(color)):
                n += 1
        return n

    def clear(self):
        """A new picture: no edits, no colors yet."""
        changed = bool(self.edits)
        self.edits, self.palette, self.selected = [], [], set()
        self._rebuild()
        return changed

    def set_palette(self, palette):
        """The colors the last trace used (engine.palette)."""
        self.palette = list(palette or [])
        self._rebuild()

    # the swatches

    def _groups(self):
        groups, by_color = [], {}
        for color, count in self.palette:
            e = engine.edit_for(color, self.edits)
            left_out = e is not None and e[1] is None
            final = color if e is None else e[1]
            if left_out:
                g = Group(color, True)
                groups.append(g)
            else:
                g = by_color.get(tuple(final))
                if g is None:
                    g = by_color[tuple(final)] = Group(tuple(final), False)
                    groups.append(g)
            g.members.append(tuple(color))
            g.count += count
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
        total = sum(c for _, c in self.palette) or 1
        present = {m for g in self.groups for m in g.members}
        self.selected &= present
        for i, g in enumerate(self.groups):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(swatch_icon(g.color, g.left_out))
            b.setIconSize(QSize(SWATCH, SWATCH))
            b.setAutoRaise(False)
            b.setStyleSheet(SWATCH_STYLE)
            b.setChecked(bool(set(g.members) & self.selected))
            share = 100.0 * g.count / total
            if g.left_out:
                tip = "%s, left out (%.1f%% of the picture)" % (hex_of(g.members[0]), share)
            elif len(g.members) > 1:
                tip = "%s: %d colors merged (%s), %.1f%% of the picture" % (
                    hex_of(g.color), len(g.members), ", ".join(hex_of(m) for m in g.members), share)
            elif g.members[0] != g.color:
                tip = "%s, traced as %s (%.1f%% of the picture)" % (hex_of(g.members[0]), hex_of(g.color), share)
            else:
                tip = "%s (%.1f%% of the picture)" % (hex_of(g.color), share)
            b.setToolTip(tip)
            b.toggled.connect(lambda on, g=g: self._toggle(g, on))
            self.grid.addWidget(b, i // COLUMNS, i % COLUMNS)
            self.buttons.append(b)
        # edits that apply to no color now (the colors were picked again): kept, they apply again
        # if a matching color comes back
        used = {id(engine.edit_for(c, self.edits)) for c, _ in self.palette}
        unused = [e for e in self.edits if id(e) not in used]
        if unused and self.palette:
            self.note.setText("%d color edit%s match%s no color now (they apply again if the color comes "
                              "back; Reset colors clears them)." % (
                                  len(unused), "" if len(unused) == 1 else "s", "es" if len(unused) == 1 else ""))
            self.note.show()
        else:
            self.note.hide()
        self._update_buttons()

    def _toggle(self, g, on):
        if on:
            self.selected |= set(g.members)
        else:
            self.selected -= set(g.members)
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

    def select_only(self, color):
        """Select the swatch of the traced color nearest to <color> (a picture's pixel)."""
        if not self.palette:
            return None
        nearest = min((c for c, _ in self.palette), key=lambda c: sum((a - b) ** 2 for a, b in zip(c, color)))
        for g in self.groups:
            if tuple(nearest) in g.members:
                self.selected = set(g.members)
                self._rebuild()
                return g
        return None

    # the edits

    def _set(self, member, to):
        """member (an original color) is traced as <to> (None: left out)."""
        self.edits = [e for e in self.edits if tuple(e[0]) != tuple(member)]
        if to is None or tuple(to) != tuple(member):
            self.edits.append((tuple(member), None if to is None else tuple(to)))
        elif engine.edit_for(member, self.edits) is not None:
            # back to its own color, but an edit made for a color a level or two off would still
            # apply: say "its own color" outright
            self.edits.append((tuple(member), tuple(member)))

    def _drop(self, member):
        """No edit applies to member any more (also one made for a color a level or two off)."""
        while True:
            e = engine.edit_for(member, self.edits)
            if e is None:
                return
            self.edits.remove(e)

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

    def merge(self):
        kept = [g for g in self._selected_groups() if not g.left_out]
        if len(kept) < 2:
            return
        target = max(kept, key=lambda g: g.count).color
        for g in kept:
            for m in g.members:
                self._set(m, target)
        self._done()

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


def set_visible_for(panel, mode):
    panel.setVisible(mode in (engine.COLORS, engine.GRAYS, engine.AUTOTRACE))
