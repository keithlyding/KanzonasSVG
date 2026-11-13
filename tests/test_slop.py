"""The slop check (tools/slop_check.py) finds nothing, and finds what it should."""

import unittest

from tests import helpers  # noqa: F401 (Qt first)
from tools import slop_check


class TestSlop(unittest.TestCase):
    def test_nothing_found(self):
        problems = slop_check.check()
        self.assertEqual(problems, [], "slop found:\n" + "\n".join(problems))

    def test_it_finds_slop(self):
        text = ("A seamless, robust way to leverage your pictures. Lorem ipsum. The colour of the "
                "the logo. Coming soon.")
        self.assertEqual(slop_check.words_found(text, slop_check.BUZZWORDS), ["seamless", "robust", "leverage"])
        self.assertEqual(slop_check.words_found(text, slop_check.PLACEHOLDERS), ["lorem ipsum", "coming soon"])
        self.assertEqual(slop_check.words_found(text, slop_check.BRITISH), ["colour"])
        self.assertTrue(slop_check.MARKERS.search("x = 1  # " + "TO" + "DO later"))
        self.assertTrue(slop_check.STRAY.search("kanzonassvg/app.py.orig"))
        self.assertTrue(slop_check.STRAY.search("tests/_quick.png"))
        # (whole words only: "robustness" in a word list isn't "robust"; "background" isn't "grey")
        self.assertEqual(slop_check.words_found("robustness, foreground", slop_check.BUZZWORDS), [])


if __name__ == "__main__":
    unittest.main()
