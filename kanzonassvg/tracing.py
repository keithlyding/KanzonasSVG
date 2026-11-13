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


COLOR_MODES = (engine.COLORS, engine.GRAYS, engine.AUTOTRACE)  # the modes whose colors can be edited


@dataclass
class Result:
    svg: str
    shapes: int
    seconds: float
    factor: int
    palette: list = None  # [((r, g, b), pixels)]: the colors traced, before color edits (engine.palette)


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
    # (the engine kept the colors it just traced with: quick)
    colors = engine.palette(data, w, h, stride, options) if options.mode in COLOR_MODES else None
    return Result(svg, n, time.perf_counter() - t, factor, colors)


# A big picture is first traced as a small copy (about a megapixel, a tenth of a second) and
# shown while the picture itself is traced: the window answers at once, even when the full
# trace of a 12-megapixel photo takes a second.
QUICK_ABOVE = 3_000_000  # pixels
QUICK_SIZE = 1_000_000


def quick_trace(img, options):
    """The SVG of a small copy of a big picture, at the picture's size, or None if it's small."""
    w, h = img.width(), img.height()
    if w * h <= QUICK_ABOVE:
        return None
    f = (QUICK_SIZE / (w * h)) ** 0.5
    from PySide6.QtCore import Qt

    small = image.to_rgba(img.scaled(max(1, round(w * f)), max(1, round(h * f)), Qt.AspectRatioMode.IgnoreAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
    svg, _n = engine.trace(*image.pixels(small), options=options)
    return set_size(svg, w, h)


def preview_image(img, options):
    """The picture as it will be traced (colors reduced), as a QImage."""
    from PySide6.QtGui import QImage

    data, w, h, stride = image.pixels(img)
    rgb = engine.preview(data, w, h, stride, options)
    return QImage(rgb, w, h, w * 3, QImage.Format.Format_RGB888).copy()
