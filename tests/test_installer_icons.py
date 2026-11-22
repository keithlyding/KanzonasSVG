"""The setup shows the right icons: the blue setup icon on its window (top left, and the
downloaded file), the orange program icon on its pages (top right while it installs or updates,
and on the first and last pages), as KanzonasPDF's setup does with its red one."""

import os
import unittest

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def blue_and_orange(img):
    """How many clearly blue and clearly orange pixels img has (a tile's colors)."""
    img = img.convert("RGBA")
    blue = orange = 0
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = img.getpixel((x, y))
            if a <= 128:
                continue
            if b > 150 and b > r + 60:
                blue += 1
            elif r > 180 and r > b + 80 and g > 60:
                orange += 1
    return blue, orange


def ico_frame(name, size):
    with Image.open(os.path.join(ASSETS, name)) as img:
        img.size = (size, size)  # Pillow picks the .ico's frame of that size
        return img.convert("RGBA")


class TestInstallerIcons(unittest.TestCase):
    def test_the_setup_uses_these_files(self):
        with open(os.path.join(ROOT, "installer", "KanzonasSVG.iss"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"(?m)^SetupIconFile=\.\.\\assets\\kanzonassvg-setup\.ico$")
        self.assertRegex(text, r"(?m)^WizardSmallImageFile=\.\.\\assets\\wizard-small\.bmp$")
        self.assertRegex(text, r"(?m)^WizardImageFile=\.\.\\assets\\wizard-large\.bmp$")

    def test_the_setup_window_icon_is_blue(self):
        for size in (16, 32, 48, 256):
            blue, orange = blue_and_orange(ico_frame("kanzonassvg-setup.ico", size))
            self.assertGreater(blue, orange, "the setup icon's %d px frame isn't blue" % size)

    def test_the_program_icon_is_orange(self):
        for size in (16, 32, 48, 256):
            blue, orange = blue_and_orange(ico_frame("kanzonassvg.ico", size))
            self.assertEqual(blue, 0, "the program icon's %d px frame has blue in it" % size)
            self.assertGreater(orange, 0)

    def test_the_setup_pages_show_the_orange_icon(self):
        for name in ("wizard-small.bmp", "wizard-large.bmp"):
            with Image.open(os.path.join(ASSETS, name)) as img:
                blue, orange = blue_and_orange(img)
            self.assertEqual(blue, 0, "%s shows the blue setup icon, not the orange one" % name)
            self.assertGreater(orange, 300, name)


if __name__ == "__main__":
    unittest.main()
