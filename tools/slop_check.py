"""The slop check: leftovers that careless or machine-written work leaves behind. Exit 1 with
a list if it finds any.

    python tools/slop_check.py

What it looks for, in our own files (core/third_party is other people's code, left alone):
- debugging left in: breakpoint(), pdb, a print( in the window's code;
- notes to self: TODO, FIXME, XXX, HACK;
- unused imports and undefined names (pyflakes; a line marked "noqa" is meant);
- functions and classes nothing uses;
- stray files tracked by git: *.orig, *.rej, *.bak, *.part, *.tmp, __pycache__, test leftovers;
- in what people read (the help, the README, release notes, the command line's help, the
  window's text): filler and buzzwords ("seamless", "robust", "leverage", "delve"...),
  placeholders (lorem ipsum, TBD, "coming soon"), British spellings (the rule: American),
  a word twice in a row;
- claims that aren't true: a menu command the help or README names that the window doesn't
  have, a link in the README to a file that isn't there, a version in CHANGELOG.md without
  its notes in RELEASE_NOTES.md.
"""

import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# words that say nothing (in our users' text, a plain word is always better)
BUZZWORDS = ["seamless", "seamlessly", "robust", "leverage", "leverages", "leveraging", "delve", "delves",
             "cutting-edge", "state-of-the-art", "game-changer", "game changer", "unlock the", "elevate your",
             "empower", "empowers", "streamline", "streamlined", "effortless", "effortlessly", "supercharge",
             "next-level", "best-in-class", "world-class", "revolutionary", "in today's", "it's worth noting",
             "it is worth noting", "in conclusion", "as an ai", "i hope this helps", "certainly!", "tapestry",
             "testament to", "navigate the complexities", "a myriad of", "plethora", "harness the power",
             "blazing fast", "blazingly", "lightning-fast", "user-friendly", "intuitive", "powerful yet"]
PLACEHOLDERS = ["lorem ipsum", "tbd", "coming soon", "placeholder", "your text here", "insert here", "foo bar",
                "example.com/your"]
# British spellings (the rule is American spelling): the word stems
BRITISH = ["colour", "behaviour", "favourite", "centre", "honour", "labour", "neighbour", "grey", "licence",
           "organise", "organisation", "recognise", "optimise", "optimisation", "realise", "analyse", "minimise",
           "maximise", "summarise", "customise", "initialise", "normalise", "visualise", "finalise", "prioritise",
           "catalogue", "dialogue", "travelled", "modelled", "labelled", "cancelling", "artefact", "aluminium"]
MARKERS = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
STRAY = re.compile(r"(\.orig|\.rej|\.bak|\.part|\.tmp|~)$|(^|/)__pycache__/|^tests/_[^/]*\.png$|\.pyc$")


def tracked():
    """The files git tracks, and new ones it would (not yet committed, not ignored): a new file's
    slop is caught before its first commit."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and os.path.exists(os.path.join(ROOT, f))]


def ours(files):
    return [f for f in files if not f.startswith("core/third_party/")]


def read(f):
    with open(os.path.join(ROOT, f), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def words_found(text, words):
    low = text.lower()
    found = []
    for w in words:
        if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
            found.append(w)
    return found


def readers_text():
    """[(where, text)] of what people read: the docs, the help, the window's and the command
    line's own words (string literals in the program)."""
    out = []
    for f in ("README.md", "RELEASE_NOTES.md", "NOTICE.md"):
        if os.path.exists(os.path.join(ROOT, f)):
            out.append((f, read(f)))
    from kanzonassvg import app
    out.append(("the help (app.HELP_HTML)", app.HELP_HTML))
    for f in ("kanzonassvg/app.py", "kanzonassvg/cli.py", "kanzonassvg/updates.py", "kanzonassvg/image.py",
              "kanzonassvg/engine.py", "kanzonassvg/tracing.py"):
        tree = ast.parse(read(f))
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        out.append((f + " (its text)", "\n|\n".join(strings)))    # (no word runs on into the next)
    return out


def check():
    problems = []
    files = tracked()
    mine = ours(files)
    py = [f for f in mine if f.endswith(".py")]
    code = [f for f in mine if f.endswith((".py", ".cpp", ".h", ".c", ".sh", ".yml", ".iss", ".spec"))]

    for f in files:
        if STRAY.search(f):
            problems.append("%s: a stray file tracked by git" % f)

    for f in code:
        if f == "tools/slop_check.py":
            continue
        for n, line in enumerate(read(f).splitlines(), 1):
            if MARKERS.search(line):
                problems.append("%s:%d: a note to self: %s" % (f, n, line.strip()[:90]))
            if re.search(r"\bbreakpoint\(\)|\bpdb\.set_trace|\bimport pdb\b", line):
                problems.append("%s:%d: debugging left in: %s" % (f, n, line.strip()[:90]))

    # the window's code talks to people through the window, never by printing
    for f in ("kanzonassvg/app.py", "kanzonassvg/updates.py", "kanzonassvg/tracing.py", "kanzonassvg/image.py",
              "kanzonassvg/engine.py"):
        for node in ast.walk(ast.parse(read(f))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
                problems.append("%s:%d: a print() in the window's code" % (f, node.lineno))

    # unused imports, undefined names
    try:
        r = subprocess.run([sys.executable, "-m", "pyflakes"] + py, cwd=ROOT, capture_output=True, text=True)
        for line in (r.stdout + r.stderr).splitlines():
            m = re.match(r"(.+?):(\d+):(?:\d+:)? (.*)", line)
            if not m:
                continue
            f, n, what = m.group(1), int(m.group(2)), m.group(3)
            src = read(f).splitlines()
            if 0 < n <= len(src) and "noqa" in src[n - 1]:
                continue
            problems.append("%s:%d: %s" % (f, n, what))
    except FileNotFoundError:
        problems.append("pyflakes isn't installed (python -m pip install pyflakes)")

    # functions and classes nothing uses (module level, in the program and the tools)
    every = "\n".join(read(f) for f in mine if f.endswith((".py", ".spec", ".yml", ".sh", ".md")))
    for f in py:
        if not f.startswith(("kanzonassvg/", "tools/")):
            continue
        for node in ast.parse(read(f)).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name not in ("main", "run"):
                if len(re.findall(r"\b%s\b" % re.escape(node.name), every)) < 2:
                    problems.append("%s:%d: %s isn't used anywhere" % (f, node.lineno, node.name))

    # what people read
    for where, text in readers_text():
        for w in words_found(text, BUZZWORDS):
            problems.append("%s: filler or a buzzword: %r" % (where, w))
        for w in words_found(text, PLACEHOLDERS):
            problems.append("%s: placeholder text: %r" % (where, w))
        for w in words_found(text, BRITISH):
            problems.append("%s: British spelling: %r (the rule: American)" % (where, w))
        for m in re.finditer(r"(?<![\w-])([A-Za-z]{2,})\s+\1(?![\w-])", text):
            if m.group(1).lower() not in ("that", "had", "is"):    # (rightly doubled sometimes)
                problems.append("%s: a word twice: %r" % (where, m.group(0)))

    # claims: menu commands named in the help and the README exist
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication(["slop-check"])
    from kanzonassvg import app
    w = app.MainWindow()
    menus = {}
    for ma in w.menuBar().actions():
        title = ma.text().replace("&", "")
        menus[title] = {a.text().replace("&", "").rstrip(".").strip() for a in ma.menu().actions() if a.text()}
    w.close()
    named = re.findall(r"<i>([A-Z][a-z]+) &gt; ([^<]+?)</i>", app.HELP_HTML)
    named += re.findall(r"\*([A-Z][a-z]+) > ([^*]+?)\*", read("README.md"))
    for menu, cmd in named:
        cmd = " ".join(cmd.split()).rstrip(".").strip()
        if menu not in menus:
            problems.append("a menu named that doesn't exist: %s > %s" % (menu, cmd))
        elif cmd not in menus[menu]:
            problems.append("a command named that isn't in the %s menu: %s > %s" % (menu, menu, cmd))

    # claims: the README's links to files here exist
    for target in re.findall(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)", read("README.md")):
        if not os.path.exists(os.path.join(ROOT, target.split("#")[0])):
            problems.append("README.md links to %s, which isn't there" % target)

    # claims: every version in the changelog has its notes
    notes = read("RELEASE_NOTES.md")
    for v in re.findall(r"^\| (\d+(?:\.\d+)+) \|", read("CHANGELOG.md"), re.M):
        # (1.0.2 was never published on its own: its notes are in 1.0.4's)
        if not re.search(r"^## %s\s*$" % re.escape(v), notes, re.M) and v not in ("1.0.2",):
            problems.append("CHANGELOG.md has %s but RELEASE_NOTES.md has no notes for it" % v)
    return problems


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    problems = check()
    for p in problems:
        print(p)
    print("slop check: %s" % ("%d found" % len(problems) if problems else "nothing found"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
