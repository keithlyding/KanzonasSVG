# KanzonasSVG: rules for every change (all AI agents and people)

This file is read by every coding agent working on this repo and by people. `CLAUDE.md`
just points here.

A picture-to-SVG program: a tracing engine in C/C++ (`core/`: Inkscape's Trace Bitmap code
with Potrace and Autotrace, fixed and freed from GTK, GLib and 2geom) behind a plain C
interface (`core/src/kzsvg.h`), and a PySide6 window and command line in Python
(`kanzonassvg/`) that call it through ctypes. `.github/workflows/build.yml` builds a Windows
zip and an installer (job `windows`, `installer/KanzonasSVG.iss`) and a Linux AppImage (job `linux`), each running the tests and a
`--selftest` inside the finished program; job `publish` releases both from `main`.

## Branches and releases
- Work on a branch of your own (`<agent>/<task>`), never straight on `main`: a push to `main`
  with a new version number publishes a release. Merge through a pull request once both
  builds on the branch are green. Never skip, disable or weaken a test to get green.
- Versions: the middle number for a new capability (1.1), the last for fixes and small
  additions (1.0.1). Take the number at merge time: merge the latest `main` first, then set
  the next one.

## Every user-facing change updates, in the same commit
1. The help (`HELP_HTML` in `kanzonassvg/app.py`, F1): new or changed settings, menu commands,
   shortcuts. The test "help mentions every menu command" fails if a menu command is missing.
2. `__version__` in `kanzonassvg/__init__.py`.
3. `CHANGELOG.md` (a row) and `RELEASE_NOTES.md` (a `## <version>` section; publishing fails
   without it).
4. `README.md` when what it says changes.

## Testing (the owner's rule, as in KanzonasPDF and KanzonasCAD: exhaustive on major revisions,
## lighter on minor ones)
Every change, minor (1.0.1, 1.0.2) or major, before pushing:
- `python tools/build_engine.py` (after any change in `core/`).
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p "test_*.py" -t .`: the unit
  tests, with short runs of the app battery, the tracing quality on the reference pictures
  against the baseline (`tools/quality.py`), and the speed budgets (`tests/test_speed.py`).
- `QT_QPA_PLATFORM=offscreen python run.py --selftest selftest.log`
- After a change in `core/`: `tests/engine_battery.sh 3000 SEED` with one or two seeds (random
  pictures and settings through the engine, with AddressSanitizer, UBSan and leak checks; it
  names the seed and step of each failure, `KZ_STEP=N` reruns one).
- After a change in the window: `python tests/battery_app.py --steps 4000 --seed S` with one or
  two seeds (odd and broken files, then random window actions; the SVG shown must be the trace
  of the picture and settings shown).
- Every build (GitHub) also runs 400 steps of the engine battery with the sanitizers and a new
  seed, the self test inside the finished programs, and installs, updates and uninstalls the
  Windows installer.

A major revision (a new middle number: 1.1, 1.2; or 2.0), before merging, adds the full checks:
`python tools/full_battery.py` (about two hours; writes `docs/test-reports/<version>.md`,
committed with the release): the engine battery with ASan/UBSan (5 seeds x 3,000) and
ThreadSanitizer (2 x 1,000), the fuzzer (30 minutes), the app battery (5 seeds x 4,000), the same
SVG on 1-8 threads, the engine's drawing against Qt's, big pictures (24-100 megapixels), the
window's speed, and the quality check with its time limits. Then, by hand: the installed
Windows program used for a while, and the AppImage on a Linux desktop (the report lists what).
Plus a break-it pass on what's new: new checks in the batteries for each new feature, so the
next runs cover it too.

Rules for all of it:
- Never skip, disable or weaken a test, battery check or budget to get green: fix the cause.
  (A check that was wrong itself, e.g. it expected exact colors from a picture with more colors
  than were asked for, is corrected with the reason in the commit.)
- A bug a battery finds gets its own regression test in the unit tests.
- `tests/reference/quality.json` changes only with a change meant to change tracing, with
  before and after numbers in the commit message.

## Speed (the owner's priority: fast, efficient, never clunky)
- The window never waits: tracing, reading picture files and drawing (both sides) happen in
  background threads, and the window only shows finished drawings (moved and scaled to the
  current view until the new one is ready). Nothing that can take more than a few
  milliseconds runs on the window's thread.
- SVGs are drawn by the engine (`core/src/drawing.cpp`, `engine.Drawing`), not by Qt's SVG
  renderer: Qt holds Python's lock while it draws, so the window froze whatever thread drew.
  Calls through ctypes let go of the lock: heavy work belongs in the engine.
- The engine uses all cores (`core/src/parallel.h`): independent rows and layers in parallel,
  progress and cancelling only on the calling thread, results in a fixed order (the same SVG
  on any number of threads: `KZ_THREADS=1` runs on one; check with ThreadSanitizer,
  `SAN="-fsanitize=thread ..." tests/engine_battery.sh`).
- The reduced colors are cached by picture and settings: a setting that doesn't change them
  must not reduce them again. The smoothed picture and its color histogram are cached by
  picture and Smooth (another number of colors starts from them). The caches hold two pictures
  (a big picture's quick-preview copy and the picture).
- A big picture (over 3 megapixels) shows a quick preview (a 1-megapixel copy traced) when its
  colors have to be reduced again, then the full trace: the window shows something within a
  few tenths of a second.
- Budgets in `tests/test_speed.py` (several times today's numbers): never weaken one to get
  green. Profile with `KZ_PROFILE=1` (the engine's steps).

## Conventions
- Tracing quality is the point: a change to the engine is measured on real pictures
  (public-domain ones, never a company's logo in the repo) before and after, with the
  numbers in the commit message. Keep colors exact (tests check them to the level).
- The engine stays dependency-free (no GLib, GTK, 2geom, Boost): it must build with Visual
  Studio on Windows and gcc/clang on Linux.
- The SVG is written with a decimal point whatever the locale (Qt sets the C library's).
- Anything platform-specific goes behind `sys.platform` and keeps the other platform's
  behavior the same. The AppImage builds on Ubuntu 22.04 and fails if a bundled file needs a
  newer glibc or C++ runtime.
- American spelling in all user-visible text.
- Logos: no Kanzonas logo is made or edited here; logos come from the Kanzonas-Site
  repository's `brand/` folder (`brand/make_logos.py`). KanzonasSVG's are copied in unchanged
  (`assets/kanzonassvg-logo.png` for the README, `kanzonassvg/logo.png` for Help > About) and
  `assets/LOGO_SOURCE.txt` records the Kanzonas-Site commit and each file's SHA-256
  (tests/test_logo_source.py fails if a file doesn't match it): to change the logo, change it
  there, copy the new files and update the record. The icons are drawn by `tools/make_icon.py` from the owner's
  cactus and sunflower (`assets/kanzonas-mark-source.png`, from KanzonasPDF, unchanged), as
  KanzonasPDF's are: orange tile and orange "SVG" tag (KanzonasPDF is red, KanzonasCAD
  purple); the installer's icon has the same orange letters on a blue tile.
- Third-party code in `core/third_party/` says where it came from and what was changed in its
  README.md; keep that true.
