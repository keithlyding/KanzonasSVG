"""KanzonasSVG in Spanish (1.4): every text translated with the same %s and %d, the window and
the help in Spanish, View > Language, the command line in English, Qt's own Spanish."""

import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from kanzonassvg import app, cli, i18n
from kanzonassvg.help_es import HELP_HTML_ES
from tests.helpers import logo


class TestCatalog(unittest.TestCase):
    def test_every_text_translated(self):
        missing, fields = i18n.untranslated("es")
        self.assertEqual(missing, [], "no Spanish for: %s" % missing[:10])
        self.assertEqual(fields, [], "Spanish with other %%-fields: %s" % fields[:10])

    def test_mode_names_and_no_leftovers(self):
        catalog = i18n.load("es")
        for label, _mode in app.MODES:             # (translated through a variable)
            self.assertIn(label, catalog)
        # every entry is a text the program shows (none left from texts since changed)
        used = set(i18n.texts_in_code()) | {label for label, _m in app.MODES}
        self.assertEqual(sorted(set(catalog) - used), [])

    def test_po_reading(self):
        po = ('msgid "One"\nmsgstr "Uno"\n\n#, fuzzy\nmsgid "Two"\nmsgstr "Dos"\n\nmsgid "Three"\nmsgstr ""\n\n'
              'msgid ""\n"Long "\n"one\\n"\nmsgstr "Larga "\n"una\\n"\n')
        self.assertEqual(i18n.parse_po(po), {"One": "Uno", "Long one\n": "Larga una\n"})


class TestSpanishWindow(unittest.TestCase):
    def setUp(self):
        QSettings("Kanzonas", app.APP_NAME).clear()
        i18n.use("es")
        self.tmp = tempfile.TemporaryDirectory()
        self.w = app.MainWindow()
        self.w.qs = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)

    def tearDown(self):
        self.w.close()
        i18n.use("en")
        self.tmp.cleanup()

    def menus(self):
        out = {}
        for ma in self.w.menuBar().actions():
            out[ma.text().replace("&", "")] = [a.text() for a in ma.menu().actions() if a.text() and not a.isSeparator()]
        return out

    def test_menus_and_panel(self):
        m = self.menus()
        self.assertEqual(list(m), ["Archivo", "Edición", "Ver", "Trazar", "Ayuda"])
        self.assertIn("Abrir imagen...", m["Archivo"])
        self.assertIn("Ajustar formas", self.w.settings.snap.text())
        self.assertEqual(self.w.settings.mode.itemText(0), "Colores")
        self.assertEqual(self.w.settings.colors.title(), "Colores")

    def test_the_spanish_help_names_every_menu_command(self):
        # as the English help (tests/test_app.py), in Spanish
        for menu, items in self.menus().items():
            for name in items:
                name = name.replace("&", "")
                if name in ("English", "Español") or name.startswith("Automático (el del sistema)"):
                    continue
                self.assertIn(name.rstrip("."), HELP_HTML_ES, "the Spanish help doesn't name %s > %s" % (menu, name))

    def test_the_help_window_in_spanish(self):
        h = self.w.show_help()
        self.assertEqual(h.windowTitle(), "Cómo usar KanzonasSVG")
        self.assertEqual(len(h.titles), len(re.findall("<h3>", app.HELP_HTML)), "chapters differ")
        self.assertEqual(h.titles[0], "Hacer un SVG")
        h.search.setText("dxf")
        self.assertRegex(h.found.text(), r"^1 de \d+$")

    def test_a_trace_in_spanish(self):
        self.w.set_image(logo(), None)
        import time
        end = time.time() + 30
        while time.time() < end and (self.w.result is None or self.w.worker is not None):
            QApplication.processEvents()
            time.sleep(0.005)
        self.assertIn(" formas, ", self.w.status.text())
        self.assertIn(" nodos", self.w.right.title)

    def test_language_menu(self):
        shown = []
        orig = app.QMessageBox.information
        app.QMessageBox.information = staticmethod(lambda *a: shown.append(a[2]))
        try:
            self.w.language_actions["en"].trigger()
        finally:
            app.QMessageBox.information = orig
        self.assertEqual(self.w.qs.value("view/language"), "en")
        self.assertEqual(shown, [app.MainWindow.RESTART["en"]])

    def test_the_command_line_stays_english(self):
        png = os.path.join(self.tmp.name, "a.png")
        logo().save(png)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.run([png, "-o", os.path.join(self.tmp.name, "a.svg")]), 0)
        self.assertIn(" shapes, ", out.getvalue())
        self.assertIn("pixels", out.getvalue())


class TestQt(unittest.TestCase):
    def test_qts_own_spanish(self):
        try:
            i18n.use("es")
            t = i18n.install_qt(QApplication.instance())
            self.assertIsNotNone(t, "no qtbase_es.qm")
            QApplication.instance().removeTranslator(t)
        finally:
            i18n.use("en")


if __name__ == "__main__":
    unittest.main()
