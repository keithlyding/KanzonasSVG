"""Windows build: Update now's two ways of putting a new version in place, run for real on the
finished program (the same steps as kanzonassvg/app.py's Update now, after the download).

    python tools/test_windows_update.py portable KanzonasSVG-windows.zip FOLDER
        unzips the zip into FOLDER, starts KanzonasSVG.exe there, then does what Update now does
        with a downloaded zip (updates.unpack, updates.swap_script); the program is closed as
        Update now closes it, and the script must copy the new files in (removing files the new
        version doesn't have), remove _update and start KanzonasSVG again.
    python tools/test_windows_update.py installer SETUP.exe FOLDER [PICTURE.png]
        with KanzonasSVG installed in FOLDER and running, runs the setup exactly as Update now
        does (updates.installer_command): it must close the running program, install over it
        (same folder) and start it again (/RELAUNCH). While it runs, its window (the progress
        window people see while updating) is captured: the blue setup icon must be at its top
        left and the orange program icon at its top right (the picture is kept in PICTURE.png).
Exit 1 with a message if anything didn't happen.
"""

import ctypes
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


def setup_windows():
    """The setup's wizard windows on the screen (Inno Setup's TWizardForm; the setup runs it
    from a second process, so they're found by their class, not the setup's process)."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if name.value == "TWizardForm" and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return found


def capture(hwnd):
    """The window as drawn (its title bar too), and where its inside starts and how wide it is:
    (QImage, x, y, width)."""
    from ctypes import wintypes
    from PySide6.QtGui import QImage
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    H = ctypes.c_void_p
    user32.GetWindowDC.restype = H
    user32.GetWindowDC.argtypes = [H]
    user32.ReleaseDC.argtypes = [H, H]
    user32.PrintWindow.argtypes = [H, H, wintypes.UINT]
    user32.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [H, ctypes.POINTER(wintypes.POINT)]
    gdi32.CreateCompatibleDC.restype = H
    gdi32.CreateCompatibleDC.argtypes = [H]
    gdi32.CreateCompatibleBitmap.restype = H
    gdi32.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = H
    gdi32.SelectObject.argtypes = [H, H]
    gdi32.GetDIBits.argtypes = [H, H, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [H]
    gdi32.DeleteDC.argtypes = [H]

    box, inside, origin = wintypes.RECT(), wintypes.RECT(), wintypes.POINT(0, 0)
    user32.GetWindowRect(hwnd, ctypes.byref(box))
    user32.GetClientRect(hwnd, ctypes.byref(inside))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    w, h = box.right - box.left, box.bottom - box.top
    if w <= 0 or h <= 0:
        return None
    dc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(dc)
    bmp = gdi32.CreateCompatibleBitmap(dc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)                 # PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    head = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = ctypes.create_string_buffer(w * h * 4)
    gdi32.SelectObject(mem, old)
    got = gdi32.GetDIBits(mem, bmp, 0, h, pixels, ctypes.byref(head), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, dc)
    if got != h:
        return None
    img = QImage(pixels.raw, w, h, w * 4, QImage.Format.Format_RGB32).copy()
    return img, origin.x - box.left, origin.y - box.top, inside.right - inside.left


def colored(img, x0, y0, x1, y1):
    """The clearly blue and the clearly orange pixels in img between (x0, y0) and (x1, y1), as
    two lists of (x, y)."""
    blue, orange = [], []
    for y in range(max(0, y0), min(img.height(), y1)):
        for x in range(max(0, x0), min(img.width(), x1)):
            c = img.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            if b > 150 and b > r + 60:
                blue.append((x, y))
            elif r > 180 and r > b + 80 and g > 60:
                orange.append((x, y))
    return blue, orange


def spread(points):
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return "x %d-%d, y %d-%d" % (min(xs), max(xs), min(ys), max(ys))


def icons_shown(shot):
    """What's wrong with the setup window's icons in a capture, or "" when they're right:
    the blue setup icon at the top left (in the title bar), the orange program icon at the
    top right (the wizard's small picture, in the band across the top of the inside).
    Blue at the top right counts only beside the icon, from the top of the inside down to the
    icon's bottom edge: below it, on the progress page, Windows draws its progress bar in blue
    (1.5.2's first build on main found one 75 pixels into that area)."""
    img, cx, cy, cw = shot
    s = max(1.0, img.devicePixelRatio())
    left_blue, _ = colored(img, 0, 0, cx + int(48 * s), cy)
    mid_blue, _ = colored(img, img.width() // 3, 0, 2 * img.width() // 3, cy)
    x0, x1 = cx + cw - int(140 * s), cx + cw
    _, orange = colored(img, x0, cy, x1, cy + int(100 * s))
    if mid_blue:
        return "the title bar is blue itself: the setup icon can't be told apart"
    if len(left_blue) < 15:
        return "no blue setup icon at the top left (%d blue pixels)" % len(left_blue)
    if len(orange) < 200:
        return "no orange program icon at the top right (%d orange pixels)" % len(orange)
    bottom = max(y for _, y in orange) + int(3 * s)
    blue, _ = colored(img, x0, cy, x1, bottom + 1)
    if len(blue) > 5:
        return ("the top right shows blue (%d pixels, %s; the orange icon %s): the blue setup icon, "
                "not the orange one" % (len(blue), spread(blue), spread(orange)))
    return ""


def installer(setup, folder, picture=None):
    if not os.path.exists(os.path.join(folder, "unins000.exe")):
        sys.exit("FAILED: not installed in " + folder)
    old = start(folder)
    cmd = updates.installer_command(os.path.abspath(setup), folder)
    print("running", " ".join(cmd), flush=True)
    run = subprocess.Popen(cmd)
    shots, end = [], time.time() + 600
    while run.poll() is None and time.time() < end:  # its window, as people updating see it
        for hwnd in setup_windows():
            time.sleep(0.3)                          # (drawn)
            shot = capture(hwnd)
            if shot:
                shots.append(shot)
        time.sleep(0.1)
    if run.poll() is None:
        run.kill()
        sys.exit("FAILED: the setup didn't finish in 10 minutes")
    if run.returncode != 0:
        sys.exit("FAILED: the setup ended with %d" % run.returncode)
    if not shots:
        sys.exit("FAILED: the setup's window never showed (Update now runs it with a progress window)")
    found = [icons_shown(s) for s in shots]
    best = shots[found.index("")] if "" in found else shots[len(shots) // 2]
    if picture:
        best[0].save(picture)
        print("the setup's window: %s" % picture)
        for i, f in enumerate(found):
            if f:                                    # (each capture that wasn't right, to look at)
                name = "%s-wrong-%d.png" % (os.path.splitext(picture)[0], i + 1)
                shots[i][0].save(name)
                print("capture %d: %s (%s)" % (i + 1, f, name))
    wrong = [f for f in found if f.startswith("the top right shows blue")]
    if wrong or "" not in found:
        sys.exit("FAILED: the setup's window icons (%d captures): %s" % (len(shots), (wrong or found)[0]))
    print("the setup's window: blue setup icon at the top left, orange program icon at the top right "
          "(%d captures)" % len(shots))
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
        installer(src, folder, sys.argv[4] if len(sys.argv) > 4 else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
