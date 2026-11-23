"""The setup shows the right icons: the blue setup icon on its window (top left, and the
downloaded file), the orange program icon on its pages (top right while it installs or updates,
and on the first and last pages), as KanzonasPDF's setup does with its red one."""

import os
import unittest

from PySide6.QtGui import QImage, QImageReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def blue_and_orange(img):
    """How many clearly blue and clearly orange pixels img (a QImage) has: a tile's colors."""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    blue = orange = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            r, g, b, a = c.red(), c.green(), c.blue(), c.alpha()
            if a <= 128:
                continue
            if b > 150 and b > r + 60:
                blue += 1
            elif r > 180 and r > b + 80 and g > 60:
                orange += 1
    return blue, orange


def ico_frames(name):
    """The frames of an .ico, by their width."""
    reader = QImageReader(os.path.join(ASSETS, name))
    frames = {}
    for i in range(reader.imageCount()):
        reader.jumpToImage(i)
        img = reader.read()
        if not img.isNull():
            frames[img.width()] = img
    return frames


def picture(name):
    img = QImage(os.path.join(ASSETS, name))
    assert not img.isNull(), name
    return img


class TestInstallerIcons(unittest.TestCase):
    def test_the_setup_uses_these_files(self):
        with open(os.path.join(ROOT, "installer", "KanzonasSVG.iss"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"(?m)^SetupIconFile=\.\.\\assets\\kanzonassvg-setup\.ico$")
        self.assertRegex(text, r"(?m)^WizardSmallImageFile=\.\.\\assets\\wizard-small\.bmp$")
        self.assertRegex(text, r"(?m)^WizardImageFile=\.\.\\assets\\wizard-large\.bmp$")

    def test_the_setup_window_icon_is_blue(self):
        frames = ico_frames("kanzonassvg-setup.ico")
        for size in (16, 32, 48, 256):
            self.assertIn(size, frames)
            blue, orange = blue_and_orange(frames[size])
            self.assertGreater(blue, orange, "the setup icon's %d px frame isn't blue" % size)

    def test_the_program_icon_is_orange(self):
        frames = ico_frames("kanzonassvg.ico")
        for size in (16, 32, 48, 256):
            self.assertIn(size, frames)
            blue, orange = blue_and_orange(frames[size])
            self.assertEqual(blue, 0, "the program icon's %d px frame has blue in it" % size)
            self.assertGreater(orange, 0)

    def test_the_setup_pages_show_the_orange_icon(self):
        for name in ("wizard-small.bmp", "wizard-large.bmp"):
            blue, orange = blue_and_orange(picture(name))
            self.assertEqual(blue, 0, "%s shows the blue setup icon, not the orange one" % name)
            self.assertGreater(orange, 300, name)


if __name__ == "__main__":
    unittest.main()
