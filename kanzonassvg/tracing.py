"""Tracing a picture with the settings the app and the command line share."""

import re
import time
from dataclasses import dataclass

from kanzonassvg import engine, image

# "Enlarge first": Auto traces small pictures at twice their size. Potrace and
# Autotrace follow pixel edges, so on a small picture curves come out lumpy; at 2x
# (smooth enlarging) they follow the shapes better. Measured on a 300-pixel-wide logo
# against the full-size original: 37% fewer badly wrong pixels at 2x, and 4x was
# hardly better than 2x.
AUTO = 0
AUTO_BELOW = 1000  # longest side, in pixels


# Enlarging never makes a picture bigger than this: a big picture gains nothing from it, and
# "4 times" on a 24-megapixel photo used to make a 384-megapixel picture (3 GB of memory)
# before refusing it as too big.
MAX_ENLARGED = 40_000_000  # pixels


def enlarge_factor(setting, width, height):
    if setting == AUTO:
        factor = 2 if max(width, height) < AUTO_BELOW else 1
    else:
        factor = max(1, min(4, int(setting)))
    while factor > 1 and width * height * factor * factor > MAX_ENLARGED:
        factor -= 1
    return factor


@dataclass
class Result:
    svg: str
    shapes: int
    seconds: float
    factor: int


_SIZE = re.compile(r'<svg ([^>]*?)width="\d+" height="\d+"')


def set_size(svg, width, height):
    """Give the SVG <width> x <height> (its viewBox, the traced pixels, stays)."""
    return _SIZE.sub(lambda m: '<svg %swidth="%d" height="%d"' % (m.group(1), width, height), svg, count=1)


def trace_image(img, options, enlarge=AUTO, progress=None):
    """Trace a QImage (RGBA8888). The SVG has the picture's own size."""
    t = time.perf_counter()
    factor = enlarge_factor(enlarge, img.width(), img.height())
    work = image.scaled(img, factor)
    data, w, h, stride = image.pixels(work)
    svg, n = engine.trace(data, w, h, stride, options, progress)
    if factor != 1:
        svg = set_size(svg, img.width(), img.height())
    return Result(svg, n, time.perf_counter() - t, factor)


def preview_image(img, options):
    """The picture as it will be traced (colors reduced), as a QImage."""
    from PySide6.QtGui import QImage

    data, w, h, stride = image.pixels(img)
    rgb = engine.preview(data, w, h, stride, options)
    return QImage(rgb, w, h, w * 3, QImage.Format.Format_RGB888).copy()
