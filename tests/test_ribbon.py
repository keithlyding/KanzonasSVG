"""The ribbon and the tools (1.5): the ribbon built from the menus' commands, with an icon for
each, fitting a 1366-pixel screen in English and Spanish; Save as SVG/PDF/EPS/DXF; the tools
(Select colors, Crop picture, Erase on the picture) one at a time, with the bar above the
picture saying what the one on does; the selected colors marked on the SVG; what a click would
select said before it; right-click menus; the wheel moving the picture (Ctrl+wheel zooming) and
not changing the settings panel's numbers it passes over."""

import os
import re
import tempfile
import time
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QToolButton

from kanzonassvg import app, i18n, icons, tracing
from kanzonassvg.ribbon import SplitButton
from tests.helpers import BLUE, RED, logo


def wheel(widget, dy, modifiers=Qt.KeyboardModifier.NoModifier, pos=None):
    pos = QPointF(pos if pos is not None else QPointF(widget.width() / 2, widget.height() / 2))
    e = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy),
                    Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, e)


class WindowTest(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.w.resize(1200, 800)
        self.w.show()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        self.tmp.cleanup()

    def traced(self):
        end = time.time() + 30
        while time.time() < end:
            QApplication.processEvents()
            if self.w.result is not None and self.w.worker is None and not self.w.timer.isActive() \
                    and not self.w.loading():
                return True
            time.sleep(0.005)
        return False

    def esc(self):
        self.w.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))


class TestRibbon(WindowTest):
    def ribbon_actions(self):
        found = set()
        for b in self.w.ribbon.findChildren(QToolButton):
            if b.defaultAction() is not None:
                found.add(b.defaultAction())
            if isinstance(b, SplitButton):
                found.update(b.menu().actions())
        return found

    def test_built_from_the_menus(self):
        menu_actions = set()

        def walk(menu):
            for a in menu.actions():
                if a.menu() is not None:
                    walk(a.menu())
                else:
                    menu_actions.add(a)
        for top in self.w.menuBar().actions():
            walk(top.menu())
        on_ribbon = self.ribbon_actions()
        self.assertGreater(len(on_ribbon), 30)
        for a in on_ribbon:
            self.assertIn(a, menu_actions, "%s is on the ribbon but in no menu" % a.text())
            self.assertFalse(a.icon().isNull(), "%s has no icon" % a.text())
        # the commands used most are all there
        for a in (self.w.a_open, self.w.a_save, self.w.a_save_dxf, self.w.a_undo, self.w.a_auto_settings,
                  self.w.a_select, self.w.a_crop, self.w.a_erase, self.w.a_change, self.w.a_merge,
                  self.w.a_leave_out, self.w.a_fit, self.w.a_outlines, self.w.a_help):
            self.assertIn(a, on_ribbon, a.text())

    def test_every_icon_is_in_the_font(self):
        for attr, name in app.MainWindow.ICONS.items():
            self.assertIn(name, icons.CODES, attr)
            self.assertFalse(icons.icon(name).isNull(), name)
        self.assertTrue(icons.icon("no-such-icon").isNull())

    def test_fits_a_small_screen(self):
        # every tab fits a 1366-pixel-wide screen (KanzonasPDF's rule), in English and Spanish
        for lang in ("en", "es"):
            i18n.use(lang)
            try:
                w = app.MainWindow()
                try:
                    for k in range(w.ribbon.count()):
                        need = w.ribbon.widget(k).widget().sizeHint().width()
                        self.assertLessEqual(need, 1366, "%s: the %s tab needs %d pixels" % (
                            lang, w.ribbon.tabText(k), need))
                finally:
                    w.close()
                    w.deleteLater()
            finally:
                i18n.use("en")

    def test_collapse(self):
        w = self.w
        full = w.ribbon.maximumHeight()
        w.a_collapse.trigger()
        self.assertLess(w.ribbon.maximumHeight(), full)
        self.assertEqual(w.qs.value("view/ribbon_collapsed"), 1)
        w.ribbon.set_collapsed(False)           # (a click on a tab opens it again)
        self.assertFalse(w.a_collapse.isChecked())
        self.assertEqual(w.ribbon.maximumHeight(), full)


class TestSaveAs(WindowTest):
    def test_each_kind_of_file(self):
        w = self.w
        for a in w.save_actions:
            self.assertFalse(a.isEnabled())
        w.set_image(logo(), None)
        self.assertTrue(self.traced())
        asked = []

        def ask(start, fmt):
            asked.append((os.path.basename(start), fmt))
            return os.path.join(self.tmp.name, "out")       # (no extension typed)
        w.ask_save_path = ask
        for a, fmt in zip(w.save_actions, ("svg", "pdf", "eps", "dxf")):
            self.assertTrue(a.isEnabled())
            a.trigger()
            w.wait_saved()
            # (the first: the picture's name; then the name saved last, as this kind)
            self.assertEqual(asked[-1], (("picture." if fmt == "svg" else "out.") + fmt, fmt))
            path = os.path.join(self.tmp.name, "out." + fmt)
            self.assertTrue(os.path.getsize(path) > 0, path)
            self.assertEqual(w.save_path, path)
        # Save: to the same file again, without asking
        n = len(asked)
        w.a_save.trigger()
        w.wait_saved()
        self.assertEqual(len(asked), n)
        # the ribbon's Save as shows the one used last
        split = [b for b in w.ribbon.findChildren(SplitButton) if w.a_save_svg in b.menu().actions()][0]
        self.assertIs(split.defaultAction(), w.a_save_dxf)

    def test_dialog_lists_only_its_kind(self):
        w = self.w
        w.set_image(logo(), None)
        self.assertTrue(self.traced())
        seen = []
        orig = app.QFileDialog.getSaveFileName
        app.QFileDialog.getSaveFileName = lambda *args: (seen.append(args), ("", ""))[1]
        try:
            self.assertFalse(w.save_as("pdf"))
        finally:
            app.QFileDialog.getSaveFileName = orig
        self.assertEqual(seen[0][3], "PDF (*.pdf)")
        self.assertTrue(seen[0][2].endswith(".pdf"))


class TestTools(WindowTest):
    def setUp(self):
        super().setUp()
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())

    def test_one_at_a_time(self):
        w = self.w
        self.assertEqual(w.tool, "select")
        self.assertTrue(w.a_select.isChecked())
        self.assertIn("Select colors", w.tool_label.text())
        w.a_erase.trigger()
        self.assertEqual(w.tool, "erase")
        self.assertTrue(w.left.erase_mode and not w.left.crop_mode)
        self.assertFalse(w.a_select.isChecked())
        self.assertIn("Erase on the picture", w.tool_label.text())
        self.assertFalse(w.eraser_slider.isHidden())
        self.assertFalse(w.tb_done.isHidden())
        w.a_crop.trigger()
        self.assertEqual(w.tool, "crop")
        self.assertTrue(w.left.crop_mode and not w.left.erase_mode)
        self.assertFalse(w.a_erase.isChecked())
        self.assertIn("Crop picture", w.tool_label.text())
        self.assertEqual(w.tb_done.text(), "Cancel")
        self.assertTrue(w.eraser_slider.isHidden())
        w.a_crop.trigger()                      # (again: off, back to selecting)
        self.assertEqual(w.tool, "select")
        w.a_erase.trigger()
        w.tb_done.click()
        self.assertEqual(w.tool, "select")
        self.assertTrue(w.tb_done.isHidden())
        # Esc: back to Select colors
        w.a_crop.trigger()
        self.esc()
        self.assertEqual(w.tool, "select")
        self.assertFalse(w.left.crop_mode)
        # a new picture: Select colors
        w.a_erase.trigger()
        w.set_image(logo(), None)
        self.assertTrue(self.traced())
        self.assertEqual(w.tool, "select")

    def test_eraser_size(self):
        w = self.w
        w.a_erase.trigger()
        w.eraser_slider.setValue(60)
        self.assertEqual(w.left.eraser, 30)
        w.a_bigger.trigger()
        self.assertEqual(w.left.eraser, 45)
        self.assertEqual(w.eraser_slider.value(), 90)
        w.a_smaller.trigger()
        self.assertEqual(w.eraser_slider.value(), 60)

    def test_no_colors_to_select(self):
        w = self.w
        s = w.settings
        s.mode.setCurrentIndex(s.mode.findData(app.engine.BRIGHTNESS))
        self.assertTrue(self.traced())
        self.assertIn("no colors to select", w.tool_label.text())
        self.assertTrue(all(b.isHidden() for b in w.tb_select))


class TestSelectingColors(WindowTest):
    def setUp(self):
        super().setUp()
        s = self.w.settings
        s.scans.setValue(3)
        self.w.a_auto_new.setChecked(False)
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())
        self.colors = self.w.settings.colors

    def red(self):
        return next(g for g in self.colors.groups if g.color[0] > 150 and g.color[2] < 100)

    def blue(self):
        return next(g for g in self.colors.groups if g.color[2] > 120 and g.color[0] < 80)

    def test_marked_on_the_svg(self):
        w = self.w
        self.assertIsNone(w.right.mark)
        self.assertFalse(w.a_change.isEnabled())
        self.colors.click_group(self.red())
        self.assertEqual(w.right.mark, (self.red().color,))
        mark = tracing.marked(w.result.svg, w.right.mark)       # (what's drawn)
        red = "#%02x%02x%02x" % self.red().color
        blue = "#%02x%02x%02x" % self.blue().color
        self.assertIn("fill:" + red, mark)          # the selected color as it is
        self.assertNotIn("fill:" + blue, mark)      # the others faded
        self.assertEqual(mark.count("<path"), w.result.svg.count("<path"))   # all in their places
        self.assertIn("selected", w.tool_label.text())
        self.assertTrue(w.a_change.isEnabled() and w.a_leave_out.isEnabled())
        self.assertFalse(w.a_merge.isEnabled())
        self.colors.click_group(self.blue(), add=True)
        self.assertTrue(w.a_merge.isEnabled())
        self.assertIn("2 colors", w.tool_label.text())
        # Esc: none selected, no mark
        self.esc()
        self.assertEqual(self.colors.selected, set())
        self.assertIsNone(w.right.mark)
        # a color left out isn't marked
        self.colors.click_group(self.red())
        w.a_leave_out.trigger()
        self.assertTrue(self.traced())
        self.assertEqual(w.a_leave_out.text(), "Put back")
        self.assertIsNone(w.right.mark)

    def test_marked_with_stack(self):
        # with Stack, a color's shape also covers the colors stacked on it: marking it must not
        # paint them its color (drawing only its shapes over the SVG did)
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
               '<g id="color-808080" inkscape:label="#808080"><path style="fill:#808080" d="M0,0H10V10H0Z"/></g>'
               '<g id="color-c80000" inkscape:label="#c80000"><path style="fill:#c80000" d="M2,2H8V8H2Z"/></g>'
               '</svg>')
        out = tracing.marked(svg, [(128, 128, 128)])
        self.assertIn('fill:#808080" d="M0,0H10V10H0Z"', out)
        self.assertNotIn("fill:#c80000", out)
        self.assertIn('d="M2,2H8V8H2Z"', out)       # still drawn, over it, faded
        self.assertEqual(re.findall(r'd="([^"]+)"', out), re.findall(r'd="([^"]+)"', svg))

    def test_hover_says_what_a_click_selects(self):
        w = self.w
        w.status.setText("before")
        w.on_hover(QPointF(50, 80))                 # over the red block
        self.assertIn("#%02x%02x%02x" % self.red().color, w.status.text())
        self.assertIn("Click", w.status.text())
        self.assertEqual(w.left.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        w.on_hover(None)
        self.assertEqual(w.status.text(), "before")
        w.a_erase.trigger()                         # (erasing: no hint, no hand)
        w.on_hover(QPointF(50, 80))
        self.assertEqual(w.status.text(), "before")
        self.assertEqual(w.left.cursor().shape(), Qt.CursorShape.CrossCursor)

    def test_right_click(self):
        w = self.w
        shown = []
        w.open_menu = lambda menu, where: shown.append([a for a in menu.actions() if not a.isSeparator()])
        w.on_picture_menu(QPointF(50, 80), QPoint(0, 0))
        self.assertEqual(self.colors._selected_groups(), [self.red()])
        for a in (w.a_change, w.a_merge, w.a_leave_out, w.a_reset_colors, w.a_crop, w.a_erase):
            self.assertIn(a, shown[-1])
        # on a swatch too
        i = self.colors.groups.index(self.blue())
        b = self.colors.buttons[i]
        b.customContextMenuRequested.emit(QPoint(2, 2))
        self.assertEqual(self.colors._selected_groups(), [self.blue()])
        self.assertEqual(len(shown), 2)
        # merge from the menu: its list opens where asked
        self.colors.click_group(self.red(), add=True)
        self.colors.open_menu = lambda menu, where: next(a for a in menu.actions() if a.data() == list(self.blue().color))
        w.a_merge.trigger()
        self.assertTrue(self.traced())
        self.assertIn("fill:#%02x%02x%02x" % self.blue().color, w.result.svg)
        self.assertNotIn("fill:#%02x%02x%02x" % tuple(RED.getRgb()[:3]), w.result.svg)
        self.assertIsNotNone(BLUE)


class TestWheel(WindowTest):
    def setUp(self):
        super().setUp()
        self.w.set_image(logo(), None)
        self.assertTrue(self.traced())

    def test_wheel_moves_ctrl_wheel_zooms(self):
        w = self.w
        scale, cx, cy = w.view.scale, w.view.cx, w.view.cy
        wheel(w.left, -120)                         # down: the picture moves up
        self.assertEqual(w.view.scale, scale)
        self.assertGreater(w.view.cy, cy)
        self.assertEqual(w.view.cx, cx)
        wheel(w.left, -120, Qt.KeyboardModifier.ShiftModifier)     # sideways
        self.assertGreater(w.view.cx, cx)
        wheel(w.right, 120, Qt.KeyboardModifier.ControlModifier)   # zooms
        self.assertAlmostEqual(w.view.scale, scale * 1.25)

    def test_panel_numbers_need_a_click(self):
        s = self.w.settings
        bar = s.verticalScrollBar()
        bar.setValue(0)
        before = s.speckles.value()
        self.assertFalse(s.speckles.hasFocus())
        wheel(s.speckles, -120)
        self.assertEqual(s.speckles.value(), before, "the wheel changed a number it passed over")
        if bar.maximum() > 0:
            self.assertGreater(bar.value(), 0, "the panel didn't scroll")
        mode = s.mode.currentIndex()
        wheel(s.mode, -120)
        self.assertEqual(s.mode.currentIndex(), mode)
        # clicked into: the wheel changes it
        s.speckles.setFocus()
        QApplication.processEvents()
        if s.speckles.hasFocus():
            wheel(s.speckles, 120)
            self.assertEqual(s.speckles.value(), before + 1)


if __name__ == "__main__":
    unittest.main()
