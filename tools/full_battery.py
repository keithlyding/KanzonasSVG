"""The full checks for a major release (a new middle number: 1.1, 1.2, 2.0): everything, long.
Writes docs/test-reports/<version>.md with each check's result and the numbers.

    python tools/full_battery.py [--quick]      (--quick: a few minutes, to try it)

Takes about two hours on a 4-core machine. Needs clang (with its sanitizer runtimes) for the
fuzzer and ThreadSanitizer, gcc or clang for the engine battery, numpy, and a built engine
(python tools/build_engine.py). Exit 1 if any check failed.

The checks (AGENTS.md, "Testing"):
 1. the unit tests (with the short batteries and the speed budgets) and the self test;
 2. tracing quality on the reference pictures against the last release's numbers, and the slop
    check (tools/slop_check.py);
 3. the engine battery with AddressSanitizer, UBSan and leak checks: 5 seeds x 3,000 steps;
 4. the engine battery with ThreadSanitizer: 2 seeds x 1,000 steps;
 5. the fuzzer: 30 minutes on 2 workers;
 6. the app battery: 5 seeds x 4,000 window steps, and the odd and broken files;
 7. the same SVG on 1, 2, 4 and 8 threads;
 8. the engine's SVG drawing against Qt's;
 9. big pictures (24, 50, 100 megapixels, enlarging);
10. the window's speed (no freeze over 0.25 s) on the reference pictures and a 12-megapixel one.
Not automatic, listed in the report to do by hand: the installed Windows program used for a
while (open, paste, every mode, zoom, save, copy into Inkscape, quit), and the AppImage on a
Linux desktop.
"""

import datetime
import os
import random
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run(name, cmd, env=None, timeout=4 * 3600):
    print("== %s: %s" % (name, " ".join(cmd)), flush=True)
    t = time.time()
    e = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    e.update(env or {})
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=e, capture_output=True, text=True, timeout=timeout)
        out, code = r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        out, code = "timed out after %d s" % timeout, -1
    lines = [ln for ln in out.splitlines() if "propagateSizeHints" not in ln and not ln.startswith(("libpng", "qt."))]
    tail = "\n".join(lines[-12:])
    ok = code == 0
    print(("PASSED" if ok else "FAILED") + " in %.0f s\n%s" % (time.time() - t, tail), flush=True)
    return {"name": name, "ok": ok, "seconds": time.time() - t, "tail": tail, "cmd": " ".join(cmd)}


def big_picture(path):
    """A 12-megapixel stand-in for a photo (the reference painting enlarged), for the speed check."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage
    QGuiApplication.instance() or QGuiApplication(["full-battery"])
    src = QImage(os.path.join(ROOT, "tests", "reference", "starry-night.jpg"))
    src.scaled(4000, 3000, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation).save(path)


def main():
    quick = "--quick" in sys.argv
    import kanzonassvg
    version = kanzonassvg.__version__
    seeds = [random.randrange(1, 10 ** 6) for _ in range(5)]
    n = (lambda full, short: short if quick else full)
    py = sys.executable
    big = os.path.join(ROOT, "build", "full-battery-12mp.png")
    os.makedirs(os.path.dirname(big), exist_ok=True)
    big_picture(big)
    ref = os.path.join(ROOT, "tests", "reference")
    checks = [
        ("Unit tests (short batteries, speed budgets)",
         [py, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-t", "."], None),
        ("Self test", [py, "run.py", "--selftest", os.path.join("build", "selftest.log")], None),
        ("Tracing quality against the last release", [py, "tools/quality.py"], None),
        ("The slop check", [py, "tools/slop_check.py"], None),
    ]
    for s in seeds[:n(5, 1)]:
        checks.append(("Engine battery, ASan/UBSan, seed %d" % s,
                       ["sh", "tests/engine_battery.sh", str(n(3000, 100)), str(s), "120"], None))
    for s in seeds[:n(2, 1)]:
        checks.append(("Engine battery, ThreadSanitizer, seed %d" % s,
                       ["sh", "tests/engine_battery.sh", str(n(1000, 50)), str(s), "300"],
                       {"SAN": "-fsanitize=thread -fno-omit-frame-pointer -g -O1",
                        "OUT": os.path.join(ROOT, "build", "battery-tsan"), "TSAN_OPTIONS": "halt_on_error=1"}))
    checks.append(("Fuzzer, %d minutes" % n(30, 1), ["sh", "tests/fuzz_engine.sh", str(n(1800, 60)), "2"], None))
    for s in seeds[:n(5, 1)]:
        checks.append(("App battery, seed %d" % s,
                       [py, "tests/battery_app.py", "--steps", str(n(4000, 200)), "--seed", str(s)], None))
    checks += [
        ("The same SVG on 1, 2, 4 and 8 threads", [py, "tools/same_threads.py"], None),
        ("The engine's SVG drawing against Qt's", [py, "tools/drawing_vs_qt.py"], None),
        ("Big pictures", [py, "tools/big_pictures.py"], None),
        ("The window's speed", [py, "tools/ui_speed.py", os.path.join(ref, "logo.png"),
                                os.path.join(ref, "starry-night.jpg"), big], None),
    ]
    results = [run(name, cmd, env) for name, cmd, env in checks]
    failed = [r for r in results if not r["ok"]]
    report = ["# Full checks: KanzonasSVG %s%s" % (version, " (quick run)" if quick else ""), "",
              "%s, %s, %d cores. Result: **%s**." % (
                  datetime.date.today().isoformat(), sys.platform, os.cpu_count() or 0,
                  "all passed" if not failed else "%d failed" % len(failed)), "",
              "| Check | Result | Time |", "|---|---|---|"]
    for r in results:
        report.append("| %s | %s | %.0f s |" % (r["name"], "passed" if r["ok"] else "**FAILED**", r["seconds"]))
    report += ["", "## By hand (not automatic)", "",
               "- [ ] The installed Windows program, used for a while: open, paste, every mode, zoom, save,",
               "      Copy SVG into Inkscape, quit.",
               "- [ ] The AppImage on a Linux desktop: the same.", "", "## Details", ""]
    for r in results:
        report += ["### %s" % r["name"], "", "`%s`" % r["cmd"], "", "```", r["tail"], "```", ""]
    path = os.path.join(ROOT, "docs", "test-reports", "%s%s.md" % (version, "-quick" if quick else ""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\nReport: %s\n%s" % (path, "ALL PASSED" if not failed else "FAILED: " + ", ".join(r["name"] for r in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
