"""The command line."""

import contextlib
import io
import os
import tempfile
import unittest

from tests import helpers  # noqa: F401
from kanzonassvg import cli, main

from tests.helpers import logo


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.run(list(args))
    return rc, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.png = os.path.join(self.dir, "logo.png")
        self.assertTrue(logo().save(self.png))

    def tearDown(self):
        self.tmp.cleanup()

    def test_next_to_the_picture(self):
        rc, out, err = run(self.png)
        self.assertEqual(rc, 0, err)
        svg = os.path.join(self.dir, "logo.svg")
        with open(svg, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("#b2002d", text)
        self.assertIn("logo.svg", out)
        # not replaced without -f
        rc, out, err = run(self.png)
        self.assertEqual(rc, 1)
        self.assertIn("-f", err)
        self.assertEqual(run(self.png, "-f", "-q")[0], 0)

    def test_options_and_named_output(self):
        dst = os.path.join(self.dir, "bw.svg")
        rc, _, err = run("--mode", "bw", "--threshold", "0.5", "--enlarge", "1", self.png, "-o", dst)
        self.assertEqual(rc, 0, err)
        with open(dst, encoding="utf-8") as f:
            self.assertIn("fill:#000000", f.read())

    def test_many_into_a_folder(self):
        second = os.path.join(self.dir, "two.png")
        logo(120, 80).save(second)
        outdir = os.path.join(self.dir, "out")
        rc, out, err = run("--colors", "3", os.path.join(self.dir, "*.png"), "-o", outdir)
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(os.listdir(outdir)), ["logo.svg", "two.svg"])

    def test_missing_and_unreadable(self):
        bad = os.path.join(self.dir, "bad.png")
        with open(bad, "wb") as f:
            f.write(b"not a picture")
        rc, _, err = run(bad, os.path.join(self.dir, "missing.png"), "-o", os.path.join(self.dir, "o"))
        self.assertEqual(rc, 1)
        self.assertIn("Can't read", err)
        self.assertIn("not found", err)

    def test_window_or_command_line(self):
        self.assertFalse(main.wants_cli([]))
        self.assertFalse(main.wants_cli(["logo.png"]))
        self.assertTrue(main.wants_cli(["--colors", "4", "logo.png"]))
        self.assertTrue(main.wants_cli(["--help"]))


if __name__ == "__main__":
    unittest.main()
