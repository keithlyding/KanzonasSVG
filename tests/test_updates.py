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
        self.assertIn("latest version", said[-1])
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
    def test_notice_and_menu(self):
        w = app.MainWindow()
        try:
            texts = [a.text() for m in w.menuBar().actions() for a in m.menu().actions()]
            self.assertIn("Check for updates...", texts)
            self.assertIn("Check for updates automatically", texts)
            w.a_auto_updates.setChecked(False)
            self.assertFalse(w.updater().enabled())
            w.a_auto_updates.setChecked(True)
            u = w.updater()
            u.manual = False
            u.release = {"tag_name": "v99.1"}
            u.releases = [u.release]
            w._update_found("99.1")
            bar = w._update_bar
            self.assertIsNotNone(bar)
            buttons = [b.text() for b in bar.findChildren(app.QPushButton)]
            # run from source: no Update now
            self.assertEqual(buttons, ["What's new", "Download", "Skip this version", "Later"])
            skip = [b for b in bar.findChildren(app.QPushButton) if b.text() == "Skip this version"][0]
            skip.click()
            self.assertIsNone(w._update_bar)
            self.assertEqual(w.qs.value(updates.KEY_SKIP), "99.1")
            w.qs.remove(updates.KEY_SKIP)
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main()
