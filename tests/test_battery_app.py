"""A short run of tests/battery_app.py on every build: the odd and broken picture files, and
300 random window actions (the full run: python tests/battery_app.py --steps 4000)."""

import os
import random
import unittest

from tests import helpers  # noqa: F401 (Qt first)
from tests import battery_app


class TestBatteryApp(unittest.TestCase):
    def test_files(self):
        fails = battery_app.check_files(random.Random(7), [])
        self.assertEqual(fails, [], "\n".join(fails))

    def test_window(self):
        seed = int(os.environ.get("KZ_BATTERY_SEED", "7"))
        fails = battery_app.check_window(300, seed, [])
        self.assertEqual(fails, [], "\n".join(fails))
        self.assertEqual(battery_app.ERRORS, [], "\n".join(battery_app.ERRORS))


if __name__ == "__main__":
    unittest.main()
