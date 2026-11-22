"""Autotrace's centerline thinning, made faster in 1.4 (it went over the whole picture on every
pass: 20 s for a scanned page at 3 times its size, an hour for a big solid area, and Cancel
didn't stop it), must give the same pixels as before: tests/thin_exact.c checks it against the
original (tests/thin_reference.c) on random pictures. Needs a C compiler (skipped without one;
the Linux build has one)."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AT = os.path.join(ROOT, "core", "third_party", "autotrace")


class TestThinning(unittest.TestCase):
    def test_same_pixels_as_the_original(self):
        cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if cc is None:
            self.skipTest("no C compiler")
        src = os.path.join(AT, "src", "autotrace")
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "thin_exact")
            subprocess.run([cc, "-O1", "-std=gnu99", "-DHAVE_CONFIG_H", "-w", "-I" + os.path.join(AT, "shim"),
                            "-I" + os.path.join(AT, "include"), "-I" + os.path.join(AT, "include", "autotrace"),
                            "-I" + src, "-I" + os.path.join(ROOT, "tests"), os.path.join(ROOT, "tests", "thin_exact.c"),
                            os.path.join(src, "exception.c"), os.path.join(src, "logreport.c"),
                            os.path.join(src, "color.c"), "-o", exe], check=True)
            for seed in ("1", "7"):
                r = subprocess.run([exe, "4000", seed], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
