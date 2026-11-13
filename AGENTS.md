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

## Before pushing
- `python tools/build_engine.py` (after any change in `core/`).
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p "test_*.py" -t .`
  (includes a short run of the app battery).
- `QT_QPA_PLATFORM=offscreen python run.py --selftest selftest.log`
- After a change in `core/`: `tests/engine_battery.sh 3000 SEED` with a few seeds (random
  pictures and settings through the engine, built with AddressSanitizer, UBSan and leak
  checks; it names the seed and step of each failure, `KZ_STEP=N` reruns one) and
  `tests/fuzz_engine.sh SECONDS` (libFuzzer; needs clang). The Linux build runs 400 steps of the
  engine battery with a new seed each time.
- After a change in the window: `python tests/battery_app.py --steps 4000 --seed S` with a few
  seeds (odd and broken picture files, then random actions in the window, checking that the
  SVG shown is the trace of the picture and settings shown).
- Never weaken a battery's check to get green: fix the cause.

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
