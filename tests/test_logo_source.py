"""The logo files are the ones Kanzonas-Site made (assets/LOGO_SOURCE.txt records them)."""

import hashlib
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestLogoSource(unittest.TestCase):
    def test_logo_files_match_the_record(self):
        with open(os.path.join(ROOT, "assets", "LOGO_SOURCE.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"commit: [0-9a-f]{40}")
        found = re.findall(r"^([\w./-]+): brand/out/\S+ sha256 ([0-9a-f]{64})$", text, re.M)
        self.assertEqual(sorted(p for p, _ in found), ["assets/kanzonassvg-logo.png", "kanzonassvg/logo.png"])
        for path, digest in found:
            with open(os.path.join(ROOT, path), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest,
                                 "%s isn't the file from Kanzonas-Site: copy it from there again" % path)


if __name__ == "__main__":
    unittest.main()
