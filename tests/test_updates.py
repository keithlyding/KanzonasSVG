"""Updates (kanzonassvg/updates.py): reading GitHub's releases, the checks on what is downloaded,
the downloads themselves (from a local web server), and putting the new version in place."""

import hashlib
import http.server
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
import zipfile

from tests import helpers  # noqa: F401 (Qt first)
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

from kanzonassvg import __version__, app, updates

SHA = "sha256:" + "0123456789abcdef" * 4


def asset(name, url=None, digest=SHA):
    a = {"name": name, "browser_download_url": url or
         "https://github.com/keithlyding/KanzonasSVG/releases/download/v9.9/" + name}
    if digest is not None:
        a["digest"] = digest
    return a


def flush():
    """Delete the finished network replies now (deleteLater), while their network objects live:
    left for the end, they crash Qt's teardown."""
    QApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait(cond, limit=20):
    end = time.time() + limit
    while time.time() < end and not cond():
        QApplication.processEvents()
        time.sleep(0.005)
    return cond()


class Files(http.server.BaseHTTPRequestHandler):
    files = {}

    def do_GET(self):
        body = self.files.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class TestReleases(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(updates.version_tuple("v1.2.3"), (1, 2, 3))
        self.assertEqual(updates.version_tuple("1.1-beta"), (1, 1))
        self.assertEqual(updates.version_tuple("x"), ())
        self.assertEqual(updates.version_tuple("1." + "9" * 20), (1,))
        self.assertEqual(updates._order((1, 1, 0)), (1, 1))

    def test_newest(self):
        rel = [{"tag_name": "v1.0"}, {"tag_name": "v9.2", "draft": True}, {"tag_name": "v9.3", "prerelease": True},
               {"tag_name": "v9.1"}, {"tag_name": "v9.0.5"}, "nonsense", {"tag_name": None}, {}]
        self.assertEqual(updates.newest_release(rel, "1.0")["tag_name"], "v9.1")
        self.assertIsNone(updates.newest_release(rel, "9.1"))
        self.assertIsNone(updates.newest_release(rel, "9.1.0"))
        self.assertIsNone(updates.newest_release([], "1.0"))
        self.assertIsNone(updates.newest_release(None, "1.0"))
        # the running version itself is never "newer"
        self.assertIsNone(updates.newest_release([{"tag_name": "v" + __version__}]))

    def test_notes(self):
        body = "intro <!-- kanzonas-notes -->\nNew: a thing\n<!-- /kanzonas-notes -->\n**Windows:** ..."
        self.assertEqual(updates.release_notes({"body": body}), "New: a thing")
        self.assertIsNone(updates.release_notes({"body": "no marks"}))
        self.assertIsNone(updates.release_notes({"body": None}))
        # a missing close mark: up to the end (and never into another block)
        self.assertEqual(updates.release_notes({"body": "<!-- kanzonas-notes --> a"}), "a")
        rel = [{"tag_name": "v9.1", "body": body, "html_url": "https://github.com/x/y/releases/tag/v9.1"},
               {"tag_name": "v9.2", "html_url": "https://evil.example/"}, {"tag_name": "v0.1"}]
        got = updates.notes_since(rel, "1.0")
        self.assertEqual([v for v, _n, _p in got], ["9.2", "9.1"])
        self.assertEqual(got[0][2], updates.RELEASES_PAGE, "a page not on github.com")
        self.assertEqual(got[1][1:], ("New: a thing", "https://github.com/x/y/releases/tag/v9.1"))
        # odd text quickly (no pattern that slows down on it)
        t = time.perf_counter()
        updates.release_notes({"body": "<!-- kanzonas-notes " * 200000})
        self.assertLess(time.perf_counter() - t, 1.0)

    def test_assets_only_from_github_with_a_digest(self):
        name = updates.PORTABLE_ZIP
        ok = {"assets": [asset(name)]}
        self.assertTrue(updates.asset_url(ok, name).startswith("https://github.com/"))
        self.assertEqual(updates.asset_digest(ok, name), SHA[7:])
        for bad in (asset(name, digest=None), asset(name, digest="md5:00"), asset(name, digest="sha256:12"),
                    asset(name, url="http://github.com/x"), asset(name, url="https://evil.example/x"),
                    asset(name, url="https://user:pw@github.com/x"), asset(name, url="https://github.com.evil.example/x")):
            self.assertIsNone(updates.asset_url({"assets": [bad]}, name), bad)
        self.assertIsNone(updates.asset_url({"assets": [asset("other")]}, name))
        for odd in (None, {}, {"assets": "x"}, {"assets": 5}, {"assets": [5]}, "x"):
            self.assertIsNone(updates.asset_url(odd, name))
        self.assertEqual(updates.update_file("installer", {"tag_name": "v1.2"}), "KanzonasSVG-v1.2-setup.exe")
        self.assertEqual(updates.update_file("appimage", {}), updates.APPIMAGE)

    def test_how_this_copy_updates(self):
        # run from source: it only tells
        self.assertFalse(updates.can_install_update())
        self.assertFalse(updates.can_self_update())
        if "APPIMAGE" not in os.environ:
            self.assertIsNone(updates.update_kind())

    def test_installer_command(self):
        cmd = updates.installer_command("setup.exe", tempfile.gettempdir())
        self.assertEqual(cmd[0], "setup.exe")
        for flag in ("/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RELAUNCH"):
            self.assertIn(flag, cmd)
        self.assertIn("/CURRENTUSER", cmd)
        self.assertFalse(any(a.startswith("/DIR") for a in cmd), "it must find the installation itself")
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "installer", "KanzonasSVG.iss"), encoding="utf-8") as f:
            iss = f.read()
        self.assertIn("RelaunchAfterUpdate", iss)
        self.assertIn(updates.UNINSTALL_KEY.split("\\")[-1].split("}")[0][1:], iss, "the setup's AppId")


class TestPortable(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def zip(self, names):
        path = os.path.join(self.dir, "u.zip")
        with zipfile.ZipFile(path, "w") as z:
            for n in names:
                z.writestr(n, "x")
        return path

    def test_unpack(self):
        new = updates.unpack(self.zip(["KanzonasSVG/KanzonasSVG.exe", "KanzonasSVG/kanzonassvg-cli.exe",
                                       "KanzonasSVG/_internal/a.dll"]), self.dir)
        self.assertEqual(new, os.path.join(self.dir, updates.STAGING, "KanzonasSVG"))
        self.assertTrue(os.path.isfile(os.path.join(new, "KanzonasSVG.exe")))

    def test_unpack_refuses(self):
        for names in (["KanzonasSVG/other.exe", "KanzonasSVG/_internal/a"], ["../evil.txt"],
                      ["KanzonasSVG/KanzonasSVG.exe", "KanzonasSVG/_internal/a", "KanzonasSVG/../../evil"]):
            with self.assertRaises(ValueError):
                updates.unpack(self.zip(names), self.dir)
            self.assertFalse(os.path.exists(os.path.join(self.dir, updates.STAGING)), "the staging folder stays")
        with open(os.path.join(self.dir, "u.zip"), "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(zipfile.BadZipFile):
            updates.unpack(os.path.join(self.dir, "u.zip"), self.dir)

    def test_swap_script(self):
        new = os.path.join(self.dir, "_update", "KanzonasSVG")
        s = updates.swap_script(4242, new, self.dir)
        self.assertIn('"PID eq 4242"', s)
        self.assertIn("/MIR", s)
        self.assertIn('start "" "%s"' % os.path.join(self.dir, "KanzonasSVG.exe"), s)
        self.assertIn('rmdir /s /q "%s"' % os.path.join(self.dir, "_update"), s)
        self.assertTrue(s.endswith("\r\n"))


class TestAppImage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_is_appimage_and_replace(self):
        old = os.path.join(self.dir, "KanzonasSVG-x86_64.AppImage")
        new = os.path.join(self.dir, ".new")
        with open(old, "wb") as f:
            f.write(b"old")
        os.chmod(old, 0o775)
        with open(new, "wb") as f:
            f.write(b"\x7fELF\x02\x01\x01\x00AI\x02rest")
        self.assertTrue(updates.is_appimage_file(new))
        self.assertFalse(updates.is_appimage_file(old))
        self.assertFalse(updates.is_appimage_file(os.path.join(self.dir, "missing")))
        updates.replace_appimage(new, old)
        self.assertFalse(os.path.exists(new))
        self.assertTrue(updates.is_appimage_file(old))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(old).st_mode), 0o755, "never writable by others")
            self.assertIsNone(updates.appimage_unwritable(old))

    def test_restart(self):
        cmd = updates.restart_command("/x/K.AppImage", pid=77)
        self.assertEqual(cmd[-2:], ["77", "/x/K.AppImage"])
        env = updates.restart_env({"APPDIR": "/tmp/.mount_K1", "APPIMAGE": "/x/K.AppImage", "OWD": "/home",
                                   "LD_LIBRARY_PATH": "/tmp/.mount_K1/usr/lib", "LD_LIBRARY_PATH_ORIG": "/opt/lib",
                                   "PATH": "/tmp/.mount_K1/usr/bin:/usr/bin", "XDG_DATA_DIRS": "/tmp/.mount_K1/share",
                                   "HOME": "/home/u"})
        self.assertEqual(env, {"LD_LIBRARY_PATH": "/opt/lib", "PATH": "/usr/bin", "HOME": "/home/u"})
        env = updates.restart_env({"APPDIR": "/tmp/appimage_extracted_abc"})
        self.assertEqual(env, {"APPIMAGE_EXTRACT_AND_RUN": "1"})

    @unittest.skipIf(sys.platform != "linux", "Linux")
    def test_restart_waits_for_the_process(self):
        import subprocess
        out = os.path.join(self.dir, "started")
        prog = os.path.join(self.dir, "prog")
        with open(prog, "w") as f:
            f.write("#!/bin/sh\ntouch '%s'\n" % out)
        os.chmod(prog, 0o755)
        sleeper = subprocess.Popen(["sleep", "0.6"])
        threading.Thread(target=sleeper.wait, daemon=True).start()   # (reaped, as its parent would)
        t = time.time()
        subprocess.run(updates.restart_command(prog, sleeper.pid), timeout=20)
        self.assertTrue(os.path.exists(out))
        self.assertGreater(time.time() - t, 0.4, "it started before the old one ended")


class TestDownloads(unittest.TestCase):
    """The updaters against a local web server (GitHub's hosts are only checked by asset_url)."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Files)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.keep = []

    def tearDown(self):
        flush()
        self.keep = []
        shutil.rmtree(self.dir, ignore_errors=True)

    def serve(self, path, data):
        Files.files[path] = data
        return self.base + path, hashlib.sha256(data).hexdigest()

    def run_updater(self, dl):
        self.keep.append(dl)
        got = {}
        dl.ready.connect(lambda p: got.setdefault("ready", p))
        dl.failed.connect(lambda m: got.setdefault("failed", m))
        dl.start()
        self.assertTrue(wait(lambda: got or (dl.reply is not None and not updates.downloading())))
        wait(lambda: bool(got), 2)
        return got

    def test_appimage(self):
        target = os.path.join(self.dir, "KanzonasSVG-x86_64.AppImage")
        with open(target, "wb") as f:
            f.write(b"old")
        data = b"\x7fELF\x02\x01\x01\x00AI\x02" + os.urandom(300000)
        url, sha = self.serve("/a.AppImage", data)
        got = self.run_updater(updates.AppImageUpdater(url, target, expected_sha256=sha))
        self.assertIn("ready", got, got)
        with open(got["ready"], "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertEqual(os.path.dirname(got["ready"]), self.dir, "not next to the AppImage")
        updates.replace_appimage(got["ready"], target)
        with open(target, "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertEqual(os.listdir(self.dir), [os.path.basename(target)])

    def test_wrong_checksum_or_file_is_never_kept(self):
        target = os.path.join(self.dir, "K.AppImage")
        open(target, "wb").close()
        url, sha = self.serve("/b.AppImage", b"\x7fELF\x02\x01\x01\x00AI\x02x")
        got = self.run_updater(updates.AppImageUpdater(url, target, expected_sha256="0" * 64))
        self.assertIn("sha256 does not match", got.get("failed", ""))
        url, sha = self.serve("/c.AppImage", b"not a program")
        got = self.run_updater(updates.AppImageUpdater(url, target, expected_sha256=sha))
        self.assertIn("isn't a KanzonasSVG AppImage", got.get("failed", ""))
        got = self.run_updater(updates.AppImageUpdater(self.base + "/missing", target, expected_sha256=sha))
        self.assertIn("download failed", got.get("failed", ""))
        got = self.run_updater(updates.AppImageUpdater(url, target, expected_sha256=None))
        self.assertIn("no sha256", got.get("failed", ""))
        self.assertEqual(os.listdir(self.dir), ["K.AppImage"], "a download stayed behind")

    def test_too_big_stops(self):
        target = os.path.join(self.dir, "K.AppImage")
        open(target, "wb").close()
        url, sha = self.serve("/big.AppImage", b"\x7fELF\x02\x01\x01\x00AI\x02" + b"x" * 200000)
        dl = updates.AppImageUpdater(url, target, expected_sha256=sha)
        dl.MAX_BYTES = 1000
        got = self.run_updater(dl)
        self.assertIn("far bigger", got.get("failed", ""))
        self.assertEqual(os.listdir(self.dir), ["K.AppImage"])

    def test_portable(self):
        buf = os.path.join(self.dir, "src.zip")
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("KanzonasSVG/KanzonasSVG.exe", "new")
            z.writestr("KanzonasSVG/_internal/a.dll", "x")
        with open(buf, "rb") as f:
            url, sha = self.serve("/p.zip", f.read())
        app_dir = os.path.join(self.dir, "app")
        os.makedirs(app_dir)
        got = self.run_updater(updates.PortableUpdater(url, app_dir, expected_sha256=sha))
        self.assertEqual(got.get("ready"), os.path.join(app_dir, updates.STAGING, "KanzonasSVG"), got)
        self.assertEqual(sorted(os.listdir(app_dir)), [updates.STAGING], "the zip stayed")

    def test_installer(self):
        url, sha = self.serve("/s.exe", b"MZ setup")
        got = self.run_updater(updates.InstallerUpdater(url, "9.9", expected_sha256=sha))
        path = got.get("ready")
        self.assertTrue(path and path.endswith("KanzonasSVG-v9.9-setup.exe"), got)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"MZ setup")
        shutil.rmtree(os.path.dirname(path))
        got = self.run_updater(updates.InstallerUpdater(url, "9.9", expected_sha256="1" * 64))
        self.assertIn("failed", got)

    def test_checker(self):
        rel = [{"tag_name": "v99.1", "assets": [asset(updates.APPIMAGE)],
                "body": "<!-- kanzonas-notes -->\nNews\n<!-- /kanzonas-notes -->"}]
        self.serve("/releases", json.dumps(rel).encode())
        self.serve("/none", b"[]")
        self.serve("/junk", b"{not json")
        qs = QSettings(os.path.join(self.dir, "s.ini"), QSettings.Format.IniFormat)
        c = updates.UpdateChecker(qs, api=self.base + "/releases")
        self.keep.append(c)
        found, said = [], []
        c.found.connect(found.append)
        c.result.connect(said.append)
        self.assertTrue(c.enabled() and c.due())
        c.check_if_due()
        self.assertTrue(wait(lambda: found))
        self.assertEqual(found, ["99.1"])
        self.assertFalse(c.manual)
        self.assertFalse(c.due(), "checked: not again for a day")
        c.check_if_due()
        QApplication.processEvents()
        self.assertFalse(c.busy())
        # skipped: an automatic check stays quiet, one asked for still tells
        qs.setValue(updates.KEY_SKIP, "99.1")
        qs.setValue(updates.KEY_LAST, time.time() + 10 * updates.DAY)     # (the clock was changed)
        self.assertTrue(c.due())
        c.check(manual=False)
        self.assertTrue(wait(lambda: not c.busy()))
        QApplication.processEvents()
        self.assertEqual(found, ["99.1"])
        c.check(manual=True)
        self.assertTrue(wait(lambda: len(found) == 2))
        self.assertTrue(c.manual)
        c.api = self.base + "/none"
        c.check()
        self.assertTrue(wait(lambda: said))
        self.assertEqual(said[-1], "You have the latest version (%s)." % __version__)
        # found nothing newer on its own: says so for the status bar, not in a box (as KanzonasPDF)
        checked = []
        c.checked.connect(checked.append)
        c.check(manual=False)
        self.assertTrue(wait(lambda: checked))
        self.assertEqual(checked, ["You have the latest version (%s)." % __version__])
        self.assertEqual(len(said), 1)
        c.api = self.base + "/junk"
        c.check()
        self.assertTrue(wait(lambda: len(said) == 2))
        self.assertIn("unexpected", said[-1])
        c.api = "http://127.0.0.1:1/x"
        c.check()
        self.assertTrue(wait(lambda: len(said) == 3))
        self.assertIn("Couldn't reach GitHub", said[-1])
        c.set_enabled(False)
        self.assertFalse(c.enabled())
        qs.setValue(updates.KEY_LAST, 0)
        c.check_if_due()
        self.assertFalse(c.busy(), "checked while switched off")


class TestWindow(unittest.TestCase):
    """The notice, the update box and their texts: the same as KanzonasPDF's (its
    kanzonas/main_window.py: _update_found, _update_box, _update_now_text, _update_outcome), for
    each way KanzonasSVG can be installed."""

    INSTALLER = ("Update now downloads the new setup, checks it, closes KanzonasSVG (save your SVG first: "
                 "it closes without asking) and installs the new version over this one; KanzonasSVG starts "
                 "again when it's done. Your settings are kept.")
    PORTABLE = ("Update now downloads it, closes KanzonasSVG (save your SVG first: it closes without "
                "asking), replaces the program files in this folder and starts it again. Your settings "
                "are kept.")
    APPIMAGE = ("Update now downloads the new AppImage, checks it, closes KanzonasSVG (save your SVG "
                "first: it closes without asking), puts it in place of KanzonasSVG-x86_64.AppImage and "
                "starts it again. Your settings are kept.")

    def setUp(self):
        from unittest import mock
        self.mock = mock
        self.w = app.MainWindow()
        self.opened = []
        self.patches = [mock.patch.object(app.QDesktopServices, "openUrl",
                                          side_effect=lambda u: self.opened.append(u.toString()))]
        for p in self.patches:
            p.start()
        u = self.w.updater()
        u.manual = False
        u.release = {"tag_name": "v99.2", "html_url": "https://github.com/keithlyding/KanzonasSVG/releases/tag/v99.2",
                     "assets": [asset(updates.setup_name("99.2")), asset(updates.PORTABLE_ZIP), asset(updates.APPIMAGE)],
                     "body": "<!-- kanzonas-notes -->\nFixed: the newest\n<!-- /kanzonas-notes -->"}
        older = {"tag_name": "v99.1", "html_url": "https://github.com/keithlyding/KanzonasSVG/releases/tag/v99.1",
                 "assets": [], "body": "no notes in this one"}
        u.releases = [u.release, older]

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.w.close()

    def kind(self, kind, all_users=False):
        """Act as a copy installed that way (None: run from source)."""
        m = self.mock
        for p in (m.patch.object(updates, "update_kind", return_value=kind),
                  m.patch.object(updates, "running_appimage", return_value="/home/me/Apps/KanzonasSVG-x86_64.AppImage"),
                  m.patch.object(updates, "for_all_users", return_value=all_users)):
            p.start()
            self.addCleanup(p.stop)

    def notice(self):
        self.w.statusBar().showMessage("something else")
        self.w._update_found("99.2")
        bar = self.w._update_bar
        self.assertIsNotNone(bar)
        self.assertEqual(self.w.statusBar().currentMessage(), "", "a status message would hide the notice")
        return bar, {b.text(): b for b in bar.findChildren(app.QPushButton)}

    def test_menu(self):
        texts = [a.text() for m in self.w.menuBar().actions() for a in m.menu().actions()]
        self.assertIn("Check for updates...", texts)
        self.assertIn("Check for updates automatically", texts)
        self.w.a_auto_updates.setChecked(False)
        self.assertFalse(self.w.updater().enabled())
        self.w.a_auto_updates.setChecked(True)

    def test_notice(self):
        for kind, text in (("installer", self.INSTALLER), ("portable", self.PORTABLE),
                           ("appimage", self.APPIMAGE), (None, None)):
            with self.subTest(kind=kind):
                self.kind(kind)
                bar, buttons = self.notice()
                label = bar.findChildren(app.QLabel)[0].text()
                self.assertEqual(label, "<b>KanzonasSVG 99.2 is available</b> (you have %s)." % __version__)
                order = [b.text() for b in bar.findChildren(app.QPushButton)]
                if kind is None:    # run from source: it can't update itself
                    self.assertEqual(order, ["What's new", "Download", "Skip this version", "Later"])
                else:
                    self.assertEqual(order, ["What's new", "Update now", "Download", "Skip this version", "Later"])
                    self.assertEqual(buttons["Update now"].toolTip(), text)
                self.assertEqual(buttons["What's new"].toolTip(), "What changed since your version")
                self.assertEqual(buttons["Download"].toolTip(),
                                 "Open the release page to download the installer or portable zip"
                                 if sys.platform == "win32" else "Open the release page to download the new version")
                buttons["Later"].click()
                self.assertIsNone(self.w._update_bar)
                self.doCleanups()

    def test_notice_buttons(self):
        self.kind("portable")
        _, b = self.notice()
        b["Skip this version"].click()
        self.assertIsNone(self.w._update_bar)
        self.assertEqual(self.w.qs.value(updates.KEY_SKIP), "99.2")
        self.w.qs.remove(updates.KEY_SKIP)
        _, b = self.notice()
        b["Download"].click()
        self.assertIsNone(self.w._update_bar)
        self.assertEqual(self.opened, ["https://github.com/keithlyding/KanzonasSVG/releases/tag/v99.2"])
        _, b = self.notice()
        with self.mock.patch.object(self.w, "update_now") as now:
            b["Update now"].click()
        now.assert_called_once()
        self.assertIsNone(self.w._update_bar)
        # What's new: the box; Update now or Download there closes the notice too, Later doesn't
        for answer, closes in (("Later", False), ("Download", True)):
            _, b = self.notice()
            with self.mock.patch.object(self.w, "run_dialog", side_effect=self.answer(answer)):
                b["What's new"].click()
            self.assertEqual(self.w._update_bar is None, closes, answer)
        self.w._close_update_bar()

    def answer(self, text):
        def run(d):
            box = d.findChild(app.QDialogButtonBox)
            self.seen = d
            [b for b in box.buttons() if b.text() == text][0].click()
        return run

    def test_box(self):
        for kind, text in (("installer", self.INSTALLER), ("portable", self.PORTABLE),
                           ("appimage", self.APPIMAGE), (None, None)):
            with self.subTest(kind=kind):
                self.kind(kind)
                shown = {}

                def look(d):
                    shown["title"] = d.windowTitle()
                    shown["size"] = (d.width(), d.height())
                    shown["labels"] = [x.text() for x in d.findChildren(app.QLabel)]
                    shown["notes"] = d.findChild(app.QTextBrowser).toMarkdown()
                    shown["buttons"] = [b.text() for b in d.findChild(app.QDialogButtonBox).buttons()]
                with self.mock.patch.object(self.w, "run_dialog", side_effect=look):
                    self.w.update_box("99.2")
                self.assertEqual(shown["title"], "Check for updates")
                self.assertEqual(shown["size"], (600, 520))
                hint = "Download opens the release page in your browser."
                self.assertEqual(shown["labels"], [
                    "KanzonasSVG 99.2 is available (you have %s)." % __version__,
                    "<b>What's new since your version</b>",
                    (text + "\n\n" + hint) if text else hint])
                notes = shown["notes"]
                self.assertIn("Version 99.2", notes)
                self.assertIn("Fixed: the newest", notes)
                self.assertIn("Version 99.1", notes)
                self.assertIn("[What's new in 99.1](https://github.com/keithlyding/KanzonasSVG/releases/tag/v99.1)", notes)
                self.assertLess(notes.index("99.2"), notes.index("99.1"))
                self.assertEqual(sorted(shown["buttons"]),
                                 sorted((["Update now"] if text else []) + ["Download", "Later"]))
                self.doCleanups()

    def test_box_buttons(self):
        self.kind("installer")
        done = []
        with self.mock.patch.object(self.w, "update_now") as now, \
                self.mock.patch.object(self.w, "run_dialog", side_effect=self.answer("Update now")):
            self.w.update_box("99.2", lambda: done.append(1))
        now.assert_called_once()
        self.assertEqual(done, [1])
        with self.mock.patch.object(self.w, "run_dialog", side_effect=self.answer("Later")):
            self.w.update_box("99.2", lambda: done.append(2))
        self.assertEqual((done, self.opened), ([1], []))
        with self.mock.patch.object(self.w, "run_dialog", side_effect=self.answer("Download")):
            self.w.update_box("99.2", lambda: done.append(3))
        self.assertEqual((done, len(self.opened)), ([1, 3], 1))
        # asked for (Help > Check for updates...): the box at once, no notice
        self.w.updater().manual = True
        with self.mock.patch.object(self.w, "update_box") as box:
            self.w._update_found("99.2")
        box.assert_called_once_with("99.2")
        self.assertIsNone(getattr(self.w, "_update_bar", None))

    def test_update_now_texts(self):
        self.kind("installer", all_users=True)
        self.assertEqual(self.w._update_now_text(), self.INSTALLER + " KanzonasSVG is installed for all users, "
                         "so Windows asks for administrator rights first.")
        self.doCleanups()
        self.kind(None)
        self.assertEqual(self.w._update_now_text(), "")
        self.assertIsNone(self.w._update_url())

    def test_failed_download_hints(self):
        self.assertEqual(self.w._update_failed_hint("installer"),
                         "You can still download the setup from the release page and run it.")
        self.assertEqual(self.w._update_failed_hint("appimage"), "You can still download KanzonasSVG-x86_64.AppImage "
                         "from the release page and put it in place of this one.")
        self.assertEqual(self.w._update_failed_hint("portable"), "You can still download KanzonasSVG-windows.zip from "
                         "the release page, unzip it and copy what's in its KanzonasSVG folder over this folder.")

    def test_update_that_didnt_finish(self):
        qs = self.w.qs
        folder = tempfile.mkdtemp(prefix="kzsvgsetup")
        setup = os.path.join(folder, updates.setup_name("99.2"))
        open(setup, "wb").close()
        updates.remember_update(qs, "99.2", setup)
        shown = []

        def look(box):
            shown.append((box.windowTitle(), box.icon(), box.text(), box.informativeText(),
                          [b.text() for b in box.buttons()]))
        with self.mock.patch.object(self.w, "run_dialog", side_effect=look):
            self.w._update_outcome()
            self.w._update_outcome()            # (told once)
        self.assertEqual(len(shown), 1)
        title, icon, text, more, buttons = shown[0]
        self.assertEqual((title, icon), ("Update", app.QMessageBox.Icon.Warning))
        self.assertEqual(text, "The update to KanzonasSVG 99.2 didn't finish: this is still %s. Windows may have "
                         "kept one of its files in use." % __version__)
        self.assertEqual(more, "Run the setup now to finish it: it shows what's in the way and can close it.")
        self.assertIn("Run the setup", buttons)
        self.assertTrue(os.path.exists(setup), "kept, to run it again")
        # it took (the version running is the one installed): nothing said, the setup removed
        updates.remember_update(qs, __version__, setup)
        with self.mock.patch.object(self.w, "run_dialog", side_effect=look):
            self.w._update_outcome()
        self.assertEqual(len(shown), 1)
        self.assertFalse(os.path.exists(folder))
        # the setup gone: download it again
        updates.remember_update(qs, "99.2", setup)
        with self.mock.patch.object(self.w, "run_dialog", side_effect=look):
            self.w._update_outcome()
        self.assertEqual(shown[1][3], "Download the setup from the release page and run it.")
        self.assertNotIn("Run the setup", shown[1][4])
        qs.setValue(updates.KEY_PENDING, "{not json")
        self.assertIsNone(updates.update_outcome(qs))
        self.assertIsNone(qs.value(updates.KEY_PENDING))


if __name__ == "__main__":
    unittest.main()
