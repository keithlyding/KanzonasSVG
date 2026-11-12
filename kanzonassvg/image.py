"""Reading pictures into RGBA pixels for the engine (with Qt, which reads PNG, JPEG, BMP,
GIF, WebP, TIFF and more)."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

# The engine's limit is 400 megapixels; this keeps memory reasonable (an image of
# 100 megapixels needs about 2 GB while tracing).
MAX_PIXELS = 100_000_000


class ImageError(Exception):
    pass


def supported_suffixes():
    return sorted({bytes(f).decode().lower() for f in QImageReader.supportedImageFormats()})


def load(path):
    """Read <path> as a QImage in RGBA8888 (not premultiplied)."""
    if not os.path.isfile(path):
        raise ImageError("File not found: %s" % path)
    reader = QImageReader(path)
    reader.setAutoTransform(True)  # photos taken sideways
    size = reader.size()
    if size.isValid() and size.width() * size.height() > MAX_PIXELS:
        raise ImageError("The picture is too big (%d x %d pixels; the limit is %d megapixels)."
                         % (size.width(), size.height(), MAX_PIXELS // 1_000_000))
    img = reader.read()
    if img.isNull():
        raise ImageError("Can't read %s: %s" % (os.path.basename(path), reader.errorString()))
    return to_rgba(img)


def to_rgba(img):
    if img.width() * img.height() > MAX_PIXELS:
        raise ImageError("The picture is too big (%d x %d pixels; the limit is %d megapixels)."
                         % (img.width(), img.height(), MAX_PIXELS // 1_000_000))
    if img.format() != QImage.Format.Format_RGBA8888:
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    return img


def scaled(img, factor):
    """<img> made <factor> times bigger, smoothly (Potrace follows smoother edges)."""
    if factor == 1:
        return img
    out = img.scaled(img.width() * factor, img.height() * factor, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    return to_rgba(out)


def pixels(img):
    """(bytes, width, height, stride) of an RGBA8888 QImage."""
    return bytes(img.constBits()), img.width(), img.height(), img.bytesPerLine()
