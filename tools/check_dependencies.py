"""Weekly security check (.github/workflows/security-check.yml): newer releases of what reads
untrusted pictures, beyond what's pinned or copied in here. pip-audit (in the same workflow)
covers known vulnerabilities in the Python packages pinned in constraints.txt; this covers what
it can't see:

- Qt (PySide6_Essentials): decodes every picture opened (PNG, JPEG, GIF, WebP, TIFF...). Qt's
  image fixes come in new releases, not always as PyPI advisories: a new release is the signal.
- Potrace and Autotrace: their code is copied into the engine (core/third_party/), so no package
  manager knows about them. Potrace: its home page's newest release, against the version copied.
  Autotrace: our copy is Inkscape's (it calls itself 0.40.0); its own project numbers releases
  0.31.x, so a tag newer than the newest one there was when this was written is the signal.

    python tools/check_dependencies.py      # prints a Markdown report; exit 1 when something's newer
"""
import json
import re
import subprocess
import sys
import urllib.request

WATCH_PYPI = ("PySide6_Essentials",)
POTRACE_COPIED = "1.16"             # core/third_party/potrace
AUTOTRACE_NEWEST_KNOWN = "0.31.11"  # the newest autotrace/autotrace tag on 2026-11-15


def pinned(path="constraints.txt"):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s#]+)", line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    return out


def key(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "kanzonassvg-security-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def pypi_rows(pins):
    rows = []
    for name in WATCH_PYPI:
        have = pins.get(name.lower())
        new = json.loads(fetch("https://pypi.org/pypi/%s/json" % name))["info"]["version"]
        if have and key(new) > key(have):
            rows.append("- **%s**: pinned %s, newest %s (https://pypi.org/project/%s/%s/)" % (name, have, new, name, new))
    return rows


def potrace_rows():
    found = re.findall(r"potrace-(\d+(?:\.\d+)+)\.tar\.gz", fetch("https://potrace.sourceforge.net/"))
    if not found:
        return ["- **Potrace**: couldn't read the newest release from https://potrace.sourceforge.net/ (look by hand)"]
    new = max(found, key=key)
    if key(new) > key(POTRACE_COPIED):
        return ["- **Potrace**: copied %s, newest %s (https://potrace.sourceforge.net/)" % (POTRACE_COPIED, new)]
    return []


def autotrace_rows():
    out = subprocess.run(["git", "ls-remote", "--tags", "https://github.com/autotrace/autotrace"],
                         capture_output=True, text=True, timeout=120)
    tags = [t.split("refs/tags/")[1] for t in out.stdout.splitlines() if "refs/tags/" in t]
    versions = [t for t in tags if re.fullmatch(r"\d+(\.\d+)+", t)]
    if out.returncode != 0 or not versions:
        return ["- **Autotrace**: couldn't read its tags from https://github.com/autotrace/autotrace (look by hand)"]
    new = max(versions, key=key)
    if key(new) > key(AUTOTRACE_NEWEST_KNOWN):
        return ["- **Autotrace**: a new release, %s (newest known %s): https://github.com/autotrace/autotrace/releases"
                % (new, AUTOTRACE_NEWEST_KNOWN)]
    return []


def main():
    rows = pypi_rows(pinned()) + potrace_rows() + autotrace_rows()
    if rows:
        print("Newer releases of what reads untrusted pictures (or that couldn't be checked):\n")
        print("\n".join(rows))
        print("\nRead their release notes for security fixes. Qt: bump the lines in constraints.txt on a "
              "branch and let the builds test it. Potrace, Autotrace: compare the fixes with the copies in "
              "core/third_party/ (their README.md says what was changed) and bring the fixes over; then "
              "update the version in tools/check_dependencies.py.")
        return 1
    print("What reads untrusted pictures is up to date (Qt %s, Potrace %s, Autotrace: no release newer than %s)."
          % (pinned().get("pyside6_essentials", "?"), POTRACE_COPIED, AUTOTRACE_NEWEST_KNOWN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
