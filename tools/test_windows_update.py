"""Windows build: Update now's two ways of putting a new version in place, run for real on the
finished program (the same steps as kanzonassvg/app.py's Update now, after the download).

    python tools/test_windows_update.py portable KanzonasSVG-windows.zip FOLDER
        unzips the zip into FOLDER, starts KanzonasSVG.exe there, then does what Update now does
        with a downloaded zip (updates.unpack, updates.swap_script); the program is closed as
        Update now closes it, and the script must copy the new files in (removing files the new
        version doesn't have), remove _update and start KanzonasSVG again.
    python tools/test_windows_update.py installer SETUP.exe FOLDER
        with KanzonasSVG installed in FOLDER and running, runs the setup exactly as Update now
        does (updates.installer_command): it must close the running program, install over it
        (same folder) and start it again (/RELAUNCH).
Exit 1 with a message if anything didn't happen.
"""

import os
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kanzonassvg import updates  # noqa: E402


def processes(folder):
    """PIDs of KanzonasSVG.exe running from folder."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-Process KanzonasSVG -ErrorAction SilentlyContinue | "
                          "ForEach-Object { \"$($_.Id)|$($_.Path)\" }"],
                         capture_output=True, text=True).stdout
    here = os.path.normcase(os.path.abspath(folder))
    pids = []
    for line in out.splitlines():
        pid, _, path = line.strip().partition("|")
        if pid.isdigit() and path and os.path.normcase(os.path.dirname(os.path.abspath(path))) == here:
            pids.append(int(pid))
    return pids


def until(cond, limit, what):
    end = time.time() + limit
    while time.time() < end:
        if cond():
            return
        time.sleep(0.5)
    sys.exit("FAILED: " + what)


def start(folder):
    p = subprocess.Popen([os.path.join(folder, updates.EXE)])
    until(lambda: p.pid in processes(folder), 60, "KanzonasSVG.exe didn't start")
    time.sleep(3)
    return p


def stop_all(folder):
    for pid in processes(folder):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


def portable(zip_path, root):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(root)
    folder = os.path.join(root, "KanzonasSVG")
    stale = os.path.join(folder, "_internal", "left-over-from-the-old-version.txt")
    with open(stale, "w") as f:
        f.write("x")
    if os.path.exists(os.path.join(folder, "unins000.exe")):
        sys.exit("FAILED: the zip has an uninstaller (it would update as an installed copy)")
    old = start(folder)
    new = updates.unpack(zip_path, folder)                  # (what PortableUpdater ends with)
    script = os.path.join(tempfile.mkdtemp(prefix="kzsvgupdate"), "kanzonassvg-update.cmd")
    with open(script, "w", encoding="mbcs") as f:
        f.write(updates.swap_script(old.pid, new, folder))
    swap = subprocess.Popen(["cmd", "/c", script], creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(3)
    if not os.path.isdir(os.path.join(folder, updates.STAGING)):
        sys.exit("FAILED: the script didn't wait for KanzonasSVG to close")
    old.kill()                                              # (Update now closes it)
    old.wait()
    swap.wait(timeout=300)
    until(lambda: not os.path.exists(os.path.join(folder, updates.STAGING)), 60, "_update wasn't removed")
    until(lambda: processes(folder), 60, "KanzonasSVG didn't start again")
    stop_all(folder)
    if os.path.exists(stale):
        sys.exit("FAILED: a file the new version doesn't have stayed in _internal")
    for name in (updates.EXE, "kanzonassvg-cli.exe"):
        if not os.path.isfile(os.path.join(folder, name)):
            sys.exit("FAILED: %s missing after the update" % name)
    print("portable update: the files swapped, _update removed, KanzonasSVG started again")


def installer(setup, folder):
    if not os.path.exists(os.path.join(folder, "unins000.exe")):
        sys.exit("FAILED: not installed in " + folder)
    old = start(folder)
    cmd = updates.installer_command(os.path.abspath(setup), folder)
    print("running", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, timeout=600)
    if r.returncode != 0:
        sys.exit("FAILED: the setup ended with %d" % r.returncode)
    if old.poll() is None:
        old.kill()
        sys.exit("FAILED: the setup didn't close the running KanzonasSVG")
    until(lambda: processes(folder), 60, "the setup didn't start KanzonasSVG again (/RELAUNCH)")
    stop_all(folder)
    print("installer update: closed, installed over it in the same folder, started again")


def main():
    kind, src, folder = sys.argv[1:4]
    if kind == "portable":
        portable(src, folder)
    else:
        installer(src, folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
