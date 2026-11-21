"""KanzonasSVG's own words in the user's language (menus, buttons, dialogs, messages, the help).

Every text the window shows goes through tr("English text"); a translation is looked up in
kanzonassvg/locale/<language>.po (the gettext format translators know) and the English is used
where there's none. The language is View > Language: Automatic (the system's), English or
Español; a change applies at the next start. Qt's own dialogs and buttons (Open, Save, Yes, No)
come translated with Qt. The command line stays in English.

Texts with numbers or names filled in keep their %s and %d (a translation has the same ones,
in the same order: tests/test_i18n.py checks).

The same as KanzonasPDF's (kanzonas/i18n.py), with the setting in KanzonasSVG's QSettings.
"""

import os
import re

LANGUAGES = {"en": "English", "es": "Español"}
_state = {"lang": None, "catalog": {}}


def _wanted():
    """The language set in View > Language ('auto', 'en', 'es'); KANZONASSVG_LANG overrides it
    (the tests run in English)."""
    env = os.environ.get("KANZONASSVG_LANG")
    if env:
        return env
    try:
        from PySide6.QtCore import QSettings
        return str(QSettings("Kanzonas", "KanzonasSVG").value("view/language", "auto") or "auto")
    except Exception:
        return "auto"


def system_language():
    try:
        from PySide6.QtCore import QLocale
        return QLocale.system().name().split("_")[0].lower()
    except Exception:
        return "en"


def language():
    """The language in use: 'en' or 'es'."""
    if _state["lang"] is None:
        want = _wanted()
        lang = system_language() if want == "auto" else want
        _state["lang"] = lang if lang in LANGUAGES else "en"
        _state["catalog"] = load(_state["lang"]) if _state["lang"] != "en" else {}
    return _state["lang"]


def use(lang):
    """Switch to lang now: the command line (always English) and the tests that check the
    Spanish window. (The window takes View > Language at its start: its texts are made then.)"""
    _state["lang"] = lang if lang in LANGUAGES else "en"
    _state["catalog"] = load(_state["lang"]) if _state["lang"] != "en" else {}


def tr(text):
    """text in the user's language (as it is when there's no translation)."""
    if _state["lang"] is None:
        language()
    return _state["catalog"].get(text) or text


def whole(n):
    """A whole number with its thousands marked as the language does (4,079; in Spanish 4.079:
    there a comma is the decimal mark, and 4,079 would read as about 4)."""
    s = "{:,}".format(int(n))
    return s.replace(",", ".") if language() == "es" else s


def po_path(lang):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale", lang + ".po")


_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _unquote(s):
    return re.sub(r'\\(.)', lambda m: _ESC.get(m.group(1), m.group(1)), s)


def parse_po(source):
    """{msgid: msgstr} of a .po file's text (untranslated and fuzzy entries left out)."""
    out = {}
    cur = {"flags": "", "msgid": None, "msgstr": None}
    field = None

    def flush():
        if cur["msgid"] and cur["msgstr"] and "fuzzy" not in cur["flags"]:
            out[cur["msgid"]] = cur["msgstr"]
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("#,"):
            if cur["msgstr"] is not None:
                flush()
                cur.update(flags="", msgid=None, msgstr=None)
            cur["flags"] += line
            continue
        if not line or line.startswith("#"):
            continue
        m = re.match(r'(msgid|msgstr)\s+"(.*)"$', line)
        if m:
            if m.group(1) == "msgid" and cur["msgstr"] is not None:
                flush()
                cur.update(flags="", msgid=None, msgstr=None)
            field = m.group(1)
            cur[field] = _unquote(m.group(2))
        elif line.startswith('"') and line.endswith('"') and field:
            cur[field] = (cur[field] or "") + _unquote(line[1:-1])
    flush()
    return out


def load(lang):
    """{English: translation} from locale/<lang>.po."""
    try:
        with open(po_path(lang), encoding="utf-8") as f:
            return parse_po(f.read())
    except OSError:
        return {}


def install_qt(app):
    """Qt's own words (standard buttons and dialogs) in the same language."""
    lang = language()
    if lang == "en":
        return None
    from PySide6.QtCore import QLibraryInfo, QTranslator
    t = QTranslator(app)
    if t.load("qtbase_" + lang, QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(t)
        return t
    return None


# for the test and translators

def texts_in_code(root=None):
    """{text: [file:line]} of every tr("...") in the package's code (literal texts only)."""
    import ast
    root = root or os.path.dirname(os.path.abspath(__file__))
    found = {}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(root, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args and \
                    isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                found.setdefault(node.args[0].value, []).append("%s:%d" % (name, node.lineno))
    return found


FIELDS = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[sdfx%]")


def untranslated(lang="es"):
    """The texts in the code with no translation in lang, and translations whose %-fields
    aren't the English's (the same, in the same order)."""
    catalog = load(lang)
    missing, fields = [], []
    for text, where in texts_in_code().items():
        if text not in catalog:
            missing.append((text, where[0]))
        elif FIELDS.findall(text) != FIELDS.findall(catalog[text]):
            fields.append((text, where[0]))
    return missing, fields
