"""Updates: asks GitHub for the newest KanzonasSVG release, tells the user, and updates in place.
The same design as KanzonasPDF's (kanzonas/updates.py), so the apps behave alike.

The automatic check runs at most once a day, in the background (Qt networking), also while
KanzonasSVG stays open for days, and fails silently when offline or blocked. It only tells:
nothing is downloaded or installed until the user clicks Update now. The box that tells about a
new version shows the short notes (RELEASE_NOTES.md, carried in each release's text between
<!-- kanzonas-notes --> marks) of every version newer than the one running.

Update now, by how KanzonasSVG was installed:
- Installed with the setup (Windows; its uninstaller sits beside the program): the release's
  setup is downloaded into a fresh folder only this user can write to, its sha256 is checked
  against the one GitHub publishes with the release, KanzonasSVG closes, and the setup runs
  quietly over the installation (its options kept) and starts KanzonasSVG again (/RELAUNCH,
  installer/KanzonasSVG.iss).
- Unzipped (Windows, KanzonasSVG-windows.zip): the zip is downloaded next to the program,
  checked the same way, unpacked into _update; KanzonasSVG closes and a small script copies the
  new files over the old ones and starts it again. The path to KanzonasSVG.exe never changes.
- The Linux AppImage: the release's KanzonasSVG-x86_64.AppImage is downloaded next to the
  running one ($APPIMAGE), checked the same way, put in its place in one step (a rename on the
  same disk), and started again once this one has closed.
Run from source, it only tells (Download opens the release page).

Settings are kept by Qt (the registry on Windows, ~/.config on Linux), never in the program's
folder, so an update can't touch them.
"""

import hashlib
import json
import math
import os
import shutil
import sys
import time
import zipfile
from urllib.parse import urlparse

from PySide6.QtCore import QCoreApplication, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from kanzonassvg import APP_NAME, __version__

REPO = "keithlyding/KanzonasSVG"
API = "https://api.github.com/repos/" + REPO + "/releases?per_page=20"
RELEASES_PAGE = "https://github.com/" + REPO + "/releases"
DAY = 24 * 3600
PORTABLE_ZIP = "KanzonasSVG-windows.zip"
APPIMAGE = "KanzonasSVG-x86_64.AppImage"    # the Linux release file (its name never changes)
EXE = "KanzonasSVG.exe"
APPIMAGE_MAX_BYTES = 1000 * 1000 * 1000     # a download past this stops (the build allows far less)
STAGING = "_update"          # folder beside the exe that holds the unpacked new version
# download hosts an update may come from: anything else is refused
GITHUB_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
# the setup's AppId (installer/KanzonasSVG.iss): its uninstall entry says who it was installed for
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{5F2EE57A-F848-4461-9769-94D17A448495}_is1"
USER_AGENT = (APP_NAME + "/" + __version__).encode()

# settings (QSettings keys)
KEY_CHECK = "updates/check"
KEY_LAST = "updates/last"
KEY_SKIP = "updates/skip"


# versions and releases

def version_tuple(text):
    """'v1.0' -> (1, 0); '1.2.3' -> (1, 2, 3). Non-numeric parts end the version (and so does a
    part too long to be one: a tag is anyone's text)."""
    parts = []
    for p in str(text).strip().lstrip("vV").split("."):
        digits = ""
        for ch in p:
            if not ch.isdigit():
                break
            digits += ch
        if not digits or len(digits) > 9:
            break
        parts.append(int(digits))
    return tuple(parts)


def _order(v):
    """A version_tuple to compare: trailing zeros don't count (1.1.0 is 1.1)."""
    v = list(v)
    while v and v[-1] == 0:
        v.pop()
    return tuple(v)


def page(release):
    """The release's GitHub page (the releases page if it has none we can use)."""
    url = (release or {}).get("html_url") if isinstance(release, dict) else None
    if isinstance(url, str) and urlparse(url).scheme == "https" and \
            (urlparse(url).hostname or "").lower() == "github.com":
        return url
    return RELEASES_PAGE


def release_version(release):
    """'1.1' for the tag v1.1."""
    return str((release or {}).get("tag_name", "")).strip().lstrip("vV")


def newest_release(releases, current=None):
    """GitHub's entry for the newest published release newer than current, or None. Drafts and
    pre-releases don't count."""
    now = _order(version_tuple(current or __version__))
    best = None
    for r in releases or []:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        v = _order(version_tuple(r.get("tag_name", "")))
        if not v or v <= now:
            continue
        if best is None or v > best[0]:
            best = (v, r)
    return best[1] if best else None


_OPEN = "<!-- kanzonas-notes -->"
_CLOSE = "<!-- /kanzonas-notes -->"


def release_notes(release):
    """The short notes in a release's text (between the kanzonas-notes marks), or None. Plain
    string searching: a release text is anyone's, so no pattern that slows down on odd input."""
    body = (release or {}).get("body") if isinstance(release, dict) else None
    if not isinstance(body, str):
        return None
    at = body.find(_OPEN)
    if at < 0:
        return None
    start = at + len(_OPEN)
    ends = [x for x in (body.find(_CLOSE, start), body.find(_OPEN, start)) if x >= 0]
    text = body[start:min(ends) if ends else len(body)].strip()
    return text or None


def notes_since(releases, current=None):
    """[(version, notes or None, page url)] for every published release newer than current,
    newest first: what changed since the version the user has."""
    now = _order(version_tuple(current or __version__))
    found = []
    for r in releases or []:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        v = _order(version_tuple(r.get("tag_name", "")))
        if v and v > now:
            found.append((v, r))
    found.sort(key=lambda x: x[0], reverse=True)
    return [(release_version(r), release_notes(r), page(r)) for _v, r in found]


def _sha256_hex(asset):
    """The hex digits of an asset digest of the form sha256:<hex>, or None."""
    digest = (asset or {}).get("digest") or ""
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return None
    hexpart = digest[len("sha256:"):]
    if len(hexpart) != 64 or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
        return None
    return hexpart.lower()


def _asset(release, name):
    assets = release.get("assets") if isinstance(release, dict) else None
    for a in assets if isinstance(assets, list) else []:
        if isinstance(a, dict) and a.get("name") == name:
            return a
    return None


def asset_url(release, name):
    """Download address of the release file called name, or None: None unless it is on a GitHub
    host, over https, and GitHub published its sha256."""
    a = _asset(release, name)
    if a is None:
        return None
    url = a.get("browser_download_url") or ""
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    if (parsed.hostname or "").lower() not in GITHUB_HOSTS or _sha256_hex(a) is None:
        return None
    return url


def asset_digest(release, name):
    """The hex sha256 GitHub published for the release file called name, or None."""
    return _sha256_hex(_asset(release, name))


def setup_name(version):
    """The release's installer for version: KanzonasSVG-v1.1-setup.exe."""
    return "KanzonasSVG-v%s-setup.exe" % version


# how this copy was installed

def app_dir():
    """The folder of the running program (frozen), or of the source."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _frozen_windows():
    return os.name == "nt" and getattr(sys, "frozen", False)


def can_install_update(folder=None):
    """A copy installed with KanzonasSVG's setup on Windows (its uninstaller sits beside it):
    Update now runs the new setup over it."""
    return _frozen_windows() and os.path.exists(os.path.join(folder or app_dir(), "unins000.exe"))


def can_self_update(folder=None):
    """An unzipped copy on Windows (KanzonasSVG-windows.zip): Update now unzips the new one over it."""
    folder = folder or app_dir()
    return (_frozen_windows() and not os.path.exists(os.path.join(folder, "unins000.exe"))
            and os.path.isfile(os.path.join(folder, EXE)))


def running_appimage():
    """The AppImage file KanzonasSVG runs from on Linux ($APPIMAGE, set by the AppImage's own
    start-up), or None. The file itself, not a link to it: the update is renamed over what it
    names, and a link replaced by the new file would leave the real one old."""
    if not sys.platform.startswith("linux"):
        return None
    path = os.environ.get("APPIMAGE") or ""
    return os.path.realpath(path) if path and os.path.isfile(path) else None


def can_update_appimage():
    return running_appimage() is not None


def update_kind():
    """'installer', 'portable', 'appimage', or None (it can only tell: run from source)."""
    if can_install_update():
        return "installer"
    if can_self_update():
        return "portable"
    if can_update_appimage():
        return "appimage"
    return None


def update_file(kind, release):
    """The release file that updates this kind of copy."""
    if kind == "installer":
        return setup_name(release_version(release))
    if kind == "portable":
        return PORTABLE_ZIP
    if kind == "appimage":
        return APPIMAGE
    return None


# Windows: the setup

def _installed_in(hive, folder):
    """The setup's uninstall entry under hive names folder as where it installed (True / False),
    or None when there's no entry (or this isn't Windows)."""
    try:
        import winreg
    except ImportError:
        return None
    here = os.path.normcase(os.path.abspath(folder)).rstrip("\\/")
    found = None
    for view in (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
        try:
            with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as k:
                where = winreg.QueryValueEx(k, "InstallLocation")[0]
        except OSError:
            continue
        found = False
        if str(where or "").strip() and \
                os.path.normcase(os.path.abspath(str(where))).rstrip("\\/") == here:
            return True
    return found


def for_all_users(folder):
    """The copy in folder was installed for all users (the setup's "all users" choice), so its
    update needs Windows' administrator prompt and the setup's /ALLUSERS (or it would install a
    second copy for this user). The setup's own uninstall entry says; without one, a folder
    under Program Files does."""
    try:
        import winreg
        mine = _installed_in(winreg.HKEY_CURRENT_USER, folder)
        everyone = _installed_in(winreg.HKEY_LOCAL_MACHINE, folder)
    except ImportError:
        mine = everyone = None
    if everyone:
        return True
    if mine:
        return False
    here = os.path.normcase(os.path.abspath(folder))
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base and here.startswith(os.path.normcase(os.path.abspath(base)) + os.sep):
            return True
    return False


def installer_command(setup_path, folder):
    """How Update now runs the new setup: quietly (a progress window only, no questions), over
    the existing installation with its options kept, closing anything still using its files,
    and starting KanzonasSVG again when done (/RELAUNCH; the Windows build runs this command)."""
    return [setup_path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CLOSEAPPLICATIONS",
            "/ALLUSERS" if for_all_users(folder) else "/CURRENTUSER", "/RELAUNCH"]


# Windows: the zip

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack(zip_path, folder):
    """Unpack a downloaded KanzonasSVG-windows.zip into folder/_update and return the folder
    holding the new KanzonasSVG.exe. Refuses a zip that isn't KanzonasSVG for Windows or that
    would write outside the staging folder."""
    stage = os.path.join(folder, STAGING)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    root = os.path.realpath(stage)
    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                raise ValueError("The download is damaged (%s). Try again." % bad)
            for name in z.namelist():
                target = os.path.realpath(os.path.join(stage, name))
                if target != root and not target.startswith(root + os.sep):
                    raise ValueError("The download contains an unsafe file name: %s" % name)
            z.extractall(stage)
        new = os.path.join(stage, "KanzonasSVG")
        if not os.path.isfile(os.path.join(new, EXE)) or not os.path.isdir(os.path.join(new, "_internal")):
            raise ValueError("The download isn't KanzonasSVG for Windows.")
    except (ValueError, OSError, zipfile.BadZipFile):
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return new


def swap_script(pid, new, folder):
    """Windows batch file text: wait for process pid to end, copy new over folder, remove the
    staging folder and start the updated program."""
    exe = os.path.join(folder, EXE)
    stage = os.path.join(folder, STAGING)
    return "\r\n".join([
        "@echo off",
        ":wait",
        'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul' % (pid, pid),
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)",
        # _internal is mirrored, so files the new version dropped go away; the top level (the two
        # programs) is copied without touching anything else in the folder
        'robocopy "%s" "%s" /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS >nul'
        % (os.path.join(new, "_internal"), os.path.join(folder, "_internal")),
        "set rc=%errorlevel%",
        'robocopy "%s" "%s" /E /XD "%s" /R:5 /W:1 /NFL /NDL /NJH /NJS >nul'
        % (new, folder, os.path.join(new, "_internal")),
        "if errorlevel 8 set rc=8",
        'rmdir /s /q "%s"' % stage,
        'if %%rc%% GEQ 8 (echo Updating KanzonasSVG failed. Unzip %s over "%s" by hand. & pause)'
        % (PORTABLE_ZIP, folder),
        'start "" "%s"' % exe,
        '(goto) 2>nul & del "%~f0"',
        ""])


# Linux: the AppImage

def appimage_unwritable(path):
    """Why this user can't replace the AppImage at path (text to show), or None when they can:
    the new file is written next to it and renamed over it, so its folder must take new files."""
    folder = os.path.dirname(os.path.abspath(path))
    if not os.access(folder, os.W_OK | os.X_OK):
        return "You don't have permission to change the folder it is in (%s)." % folder
    try:
        import stat
        st = os.stat(folder)
        if st.st_mode & stat.S_ISVTX and os.stat(path).st_uid != os.getuid() and st.st_uid != os.getuid():
            return "It belongs to another user."    # (a shared folder like /tmp)
    except OSError as e:
        return str(e)
    return None


def is_appimage_file(path):
    """The file at path is a Linux program packed as an AppImage (type 2: an ELF program with
    AI 2 in its header)."""
    try:
        with open(path, "rb") as f:
            head = f.read(11)
    except OSError:
        return False
    return head[:4] == b"\x7fELF" and head[8:11] == b"AI\x02"


def replace_appimage(new, target):
    """Put the checked new AppImage at target in one step: executable like the old one (and by
    its owner in any case; never changeable by other users), then renamed over it. The running
    program keeps its own copy open until it ends."""
    try:
        mode = os.stat(target).st_mode & 0o777
    except OSError:
        mode = 0o755
    os.chmod(new, (mode | 0o100) & ~0o022)
    os.replace(new, target)


def restart_command(target, pid=None):
    """The command that starts the new AppImage once this process (pid) has ended (at most 30 s)."""
    pid = os.getpid() if pid is None else pid
    wait = 'i=0; while kill -0 "$1" 2>/dev/null && [ "$i" -lt 150 ]; do sleep 0.2; i=$((i+1)); done; exec "$2"'
    return ["/bin/sh", "-c", wait, "kz-restart", str(pid), target]


def restart_env(env=None):
    """The environment to start the new AppImage with: without what this AppImage's start-up set
    for itself (its folder, which goes away when it ends, and the library path PyInstaller
    changed; its earlier value comes back from the LD_LIBRARY_PATH_ORIG copy)."""
    env = dict(os.environ if env is None else env)
    mount = env.get("APPDIR") or ""
    if os.path.basename(mount.rstrip("/")).startswith("appimage_extracted_"):
        # started with --appimage-extract-and-run (no FUSE here): the new one must be too
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    for key in ("APPIMAGE", "APPDIR", "ARGV0", "OWD", "DESKTOP_STARTUP_ID", "XDG_ACTIVATION_TOKEN"):
        env.pop(key, None)
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        if key + "_ORIG" in env:
            env[key] = env.pop(key + "_ORIG")
    if mount:
        mount = mount.rstrip("/")
        for key, value in list(env.items()):
            parts = value.split(os.pathsep)
            kept = [p for p in parts if not (p == mount or p.startswith(mount + "/"))]
            if kept != parts:
                if any(kept):
                    env[key] = os.pathsep.join(kept)
                else:
                    del env[key]
    return env


# the check

class UpdateChecker(QObject):
    """found(version) when a newer release exists (self.release is its entry, self.releases every
    release listed); result(text) answers a check the user asked for."""
    found = Signal(str)
    result = Signal(str)

    def __init__(self, settings, parent=None, api=API):
        super().__init__(parent)
        self.settings = settings
        self.api = api
        self.net = None
        self.manual = False
        self.release = None
        self.releases = []
        self._reply = None
        self._reply_manual = False

    def enabled(self):
        return str(self.settings.value(KEY_CHECK, "true")).lower() not in ("false", "0")

    def set_enabled(self, on):
        self.settings.setValue(KEY_CHECK, "true" if on else "false")

    def due(self):
        try:
            last = float(self.settings.value(KEY_LAST, 0) or 0)
        except (TypeError, ValueError):
            last = 0
        now = time.time()
        # (a time in the future: the clock was changed; check rather than wait)
        return not math.isfinite(last) or last > now or now - last >= DAY

    def check_if_due(self):
        if self.enabled() and self.due():
            self.check(manual=False)

    def busy(self):
        return self._reply is not None and self._reply.isRunning()

    def check(self, manual=True):
        if self.busy():
            if not manual or self._reply_manual:
                return                  # (one is already on its way)
            old, self._reply = self._reply, None
            old.abort()                 # asked for while the automatic one runs: this one
        if self.net is None:
            self.net = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(self.api))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", USER_AGENT)
        req.setTransferTimeout(15000)
        reply = self.net.get(req)
        self._reply, self._reply_manual = reply, manual
        reply.finished.connect(lambda: self._done(reply, manual))

    def _done(self, reply, manual):
        reply.deleteLater()
        if self._reply is reply:
            self._reply = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            if manual and reply.error() != QNetworkReply.NetworkError.OperationCanceledError:
                self.result.emit("Couldn't reach GitHub to check for updates (%s)." % reply.errorString())
            return
        raw = bytes(reply.readAll())
        try:
            data = json.loads(raw.decode("utf-8")) if len(raw) < 20 * 1000 * 1000 else None
        except (ValueError, RecursionError):
            data = None
        if not isinstance(data, list):
            if manual:
                self.result.emit("GitHub sent an unexpected answer. Try again later.")
            return
        self.settings.setValue(KEY_LAST, time.time())
        self.manual = manual
        self.releases = data
        self.release = newest_release(data)
        if self.release is None:
            if manual:
                self.result.emit("You have the latest version (%s)." % __version__)
            return
        version = release_version(self.release)
        if not manual and str(self.settings.value(KEY_SKIP, "")) == version:
            return
        self.found.emit(version)


# the download

_RUNNING = []                           # the downloads on their way (one at a time)


def downloading():
    """An update is being downloaded (Update now waits for it rather than start another)."""
    return any(not st["done"] for st in _RUNNING)


def _abandon(st):
    """The download's window went away or KanzonasSVG quit before it finished: nothing of it
    stays behind (its file, and its own folder)."""
    if st["done"]:
        return
    st["done"] = True
    if st in _RUNNING:
        _RUNNING.remove(st)
    try:
        if st["file"] is not None:
            st["file"].close()
    except OSError:
        pass
    for path in st["paths"]:
        try:
            os.remove(path)
        except OSError:
            pass
    for folder in st["folders"]:
        shutil.rmtree(folder, ignore_errors=True)


class PortableUpdater(QObject):
    """Downloads the Windows zip next to the program, checks its sha256 and unpacks it.
    progress(received, total); ready(folder of the new version); failed(message)."""
    progress = Signal(int, int)
    ready = Signal(str)
    failed = Signal(str)
    MAX_BYTES = APPIMAGE_MAX_BYTES

    def __init__(self, url, folder, parent=None, expected_sha256=None):
        super().__init__(parent)
        self.url, self.folder = url, folder
        self.expected_sha256 = expected_sha256
        self.net = QNetworkAccessManager(self)
        self.reply = None
        self.file = None
        self.path = None
        self._failed_write = None       # the error writing the download met (disk full...)
        self._too_big = False
        self._good = False

    def _expected_hex(self):
        text = (self.expected_sha256 or "").strip().lower()
        if text.startswith("sha256:"):
            text = text[len("sha256:"):]
        if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
            return ""
        return text

    def start(self):
        if not self._expected_hex():
            self.failed.emit("The update was not applied: the release has no sha256 digest.")
            return
        try:
            self.file = self._open()
        except OSError as e:
            self.failed.emit(self._write_error(e))
            return
        st = self._state = {"done": False, "file": self.file, "paths": [self.path], "folders": self._folders()}
        _RUNNING.append(st)
        # (not methods of self: they run while self is being destroyed)
        self.destroyed.connect(lambda *_: _abandon(st))
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(lambda: _abandon(st))
        req = QNetworkRequest(QUrl(self.url))
        req.setRawHeader(b"User-Agent", USER_AGENT)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(60000)
        self.reply = self.net.get(req)
        self.reply.readyRead.connect(lambda: self._write(bytes(self.reply.readAll())))
        self.reply.downloadProgress.connect(self._progress)
        self.reply.finished.connect(self._done)

    def cancel(self):
        if self.reply is not None and self.reply.isRunning():
            self.reply.abort()

    def _progress(self, received, total):
        if not self._too_big and max(received, total) > self.MAX_BYTES:
            self._too_big = True        # (it would fill the disk)
            self.reply.abort()
            return
        self.progress.emit(int(received), int(total))

    def _write(self, data):
        if self._failed_write is not None or self.file is None:
            return
        try:
            self.file.write(data)
        except OSError as e:
            # the disk filled up or the folder went away: stop; _done says so and cleans up
            self._failed_write = e
            if self.reply is not None and self.reply.isRunning():
                self.reply.abort()

    def _done(self):
        st = getattr(self, "_state", None)
        if st is not None:
            if st["done"]:
                return                  # (already cleared away: KanzonasSVG is quitting)
            st["done"] = True
            if st in _RUNNING:
                _RUNNING.remove(st)
        r = self.reply
        r.deleteLater()
        self._write(bytes(r.readAll()))
        try:
            self.file.close()
        except OSError as e:
            if self._failed_write is None:
                self._failed_write = e
        try:
            if self._failed_write is not None:
                self.failed.emit(self._write_error(self._failed_write))
                return
            if self._too_big:
                self.failed.emit("The download was stopped: it is far bigger than KanzonasSVG.")
                return
            if r.error() != QNetworkReply.NetworkError.NoError:
                if r.error() != QNetworkReply.NetworkError.OperationCanceledError:
                    self.failed.emit("The download failed (%s)." % r.errorString())
                return
            if file_sha256(self.path) != self._expected_hex():
                self.failed.emit("The download was not applied: its sha256 does not match the release.")
                return
            try:
                result = self._finish()
            except (ValueError, OSError, zipfile.BadZipFile) as e:
                self.failed.emit(str(e))
                return
            self._good = True
            self.ready.emit(result)
        finally:
            self._cleanup()

    # what InstallerUpdater and AppImageUpdater do differently

    def _write_error(self, e):
        return "Can't write next to %s (%s)." % (EXE, e)

    def _open(self):
        self.path = os.path.join(self.folder, STAGING + ".zip")
        return open(self.path, "wb")

    def _folders(self):
        return []

    def _finish(self):
        return unpack(self.path, self.folder)

    def _cleanup(self):
        try:
            os.remove(self.path)        # (the zip is unpacked by now, or no good)
        except OSError:
            pass


class InstallerUpdater(PortableUpdater):
    """Downloads the new setup for an installed copy into a fresh folder only this user can write
    to, and checks its sha256. ready(path of the setup)."""

    def __init__(self, url, version, parent=None, expected_sha256=None):
        super().__init__(url, "", parent, expected_sha256)
        self.version = version

    def _write_error(self, e):
        return "Can't save the new setup (%s)." % e

    def _open(self):
        import tempfile
        self.path = os.path.join(tempfile.mkdtemp(prefix="kzsvgsetup"), setup_name(self.version))
        return open(self.path, "wb")

    def _folders(self):
        return [os.path.dirname(self.path)]

    def _finish(self):
        return self.path

    def _cleanup(self):
        if not self._good:              # a failed or wrong download goes, with its folder
            shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)


class AppImageUpdater(PortableUpdater):
    """Downloads the new AppImage next to the running one (the same disk: the rename that puts it
    in place is a single step) and checks its sha256 and that it is an AppImage. ready(path of
    the checked download); the caller puts it in place with replace_appimage."""

    def __init__(self, url, appimage, parent=None, expected_sha256=None):
        super().__init__(url, os.path.dirname(os.path.abspath(appimage)), parent, expected_sha256)
        self.appimage = os.path.abspath(appimage)

    def _write_error(self, e):
        return "Can't write next to %s (%s)." % (os.path.basename(self.appimage), e)

    def _open(self):
        # a new file only this user can read or change, under a name nobody can guess, never
        # through a link: the folder may be shared, and someone else who can add files there could
        # otherwise prepare the name (a link to another of the user's files)
        import tempfile
        fd, self.path = tempfile.mkstemp(prefix=".%s.update-" % os.path.basename(self.appimage), dir=self.folder)
        return os.fdopen(fd, "wb")

    def _finish(self):
        if not is_appimage_file(self.path):
            raise ValueError("The download isn't a KanzonasSVG AppImage.")
        return self.path

    def _cleanup(self):
        if not self._good:
            super()._cleanup()
