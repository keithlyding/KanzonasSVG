# PyInstaller spec: one folder with the window program (KanzonasSVG) and, on Windows, a
# console program for the command line (kanzonassvg-cli.exe) sharing the same files.
#   python -m PyInstaller --noconfirm packaging/kanzonassvg.spec
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
WINDOWS = sys.platform == "win32"
ENGINE = "kzsvg.dll" if WINDOWS else "libkzsvg.so"
engine = os.path.join(ROOT, "kanzonassvg", "lib", ENGINE)
if not os.path.exists(engine):
    raise SystemExit("Build the engine first: python tools/build_engine.py")

# Only the parts of Qt the app uses
EXCLUDES = ["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf",
            "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtOpenGL",
            "PySide6.QtDBus", "PySide6.QtXml", "PySide6.QtSql", "PySide6.QtTest", "unittest", "pydoc"]

runtime_hooks = [] if WINDOWS else [os.path.join(ROOT, "packaging", "linux", "pyi_rth_linux_env.py")]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[(engine, "kanzonassvg/lib")],
    datas=[(os.path.join(ROOT, "kanzonassvg", "icon.png"), "kanzonassvg"),
           (os.path.join(ROOT, "kanzonassvg", "logo.png"), "kanzonassvg")],
    hiddenimports=["kanzonassvg.app", "kanzonassvg.cli", "kanzonassvg.selftest", "PySide6.QtSvg"],
    excludes=EXCLUDES,
    runtime_hooks=runtime_hooks,
)
pyz = PYZ(a.pure)
icon = os.path.join(ROOT, "assets", "kanzonassvg.ico") if WINDOWS else None

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="KanzonasSVG", console=not WINDOWS, icon=icon,
          upx=False)
programs = [gui]
if WINDOWS:
    programs.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name="kanzonassvg-cli", console=True,
                        icon=icon, upx=False))
coll = COLLECT(*programs, a.binaries, a.datas, upx=False, name="KanzonasSVG")
