"""Tracing quality on the reference pictures stays as good as the last release's
(tools/quality.py; its time limits are left to the full checks, as build machines vary)."""

import json
import os
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from tools import quality


class TestQuality(unittest.TestCase):
    def test_as_good_as_the_baseline(self):
        with open(quality.BASELINE, encoding="utf-8") as f:
            base = json.load(f)
        worse = []
        for key, now in quality.measure().items():
            was = base[key]
            if now["badly_wrong_pct"] > was["badly_wrong_pct"] + max(0.02, 0.05 * was["badly_wrong_pct"]):
                worse.append("%s: %.3f%% badly wrong, was %.3f%%" % (key, now["badly_wrong_pct"], was["badly_wrong_pct"]))
        self.assertEqual(worse, [], "\n".join(worse))


if __name__ == "__main__":
    unittest.main()
