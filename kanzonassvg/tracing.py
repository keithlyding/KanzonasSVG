"""Tracing a picture with the settings the app and the command line share."""

import re
import time
from dataclasses import dataclass

from kanzonassvg import engine, export, image
from kanzonassvg.i18n import tr

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
# Autotrace (Autotrace and Centerline) traces pictures up to this wide and high (the engine
# refuses bigger ones); enlarging never goes past it either.
AUTOTRACE_MAX_SIDE = 65535  # pixels


def enlarge_factor(setting, width, height):
    if setting == AUTO:
        factor = 2 if max(width, height) < AUTO_BELOW else 1
    else:
        factor = max(1, min(4, int(setting)))
    while factor > 1 and (width * height * factor * factor > MAX_ENLARGED
                          or max(width, height) * factor > AUTOTRACE_MAX_SIDE):
        factor -= 1
    return factor


COLOR_MODES = (engine.COLORS, engine.GRAYS, engine.AUTOTRACE)  # the modes whose colors can be edited


@dataclass
class Result:
    svg: str
    shapes: int
    seconds: float
    factor: int
    palette: list = None  # [((r, g, b), pixels, is_background)]: the colors traced, before edits (engine.palette)
    background: bytes = None  # the background's pixels in the picture traced (w x h at factor), 1 each

    def in_background(self, x, y):
        """The picture's pixel (x, y) is in the background (as the colors were traced)."""
        if not self.background:
            return False
        w = len(self.background) // max(1, self._h)
        tx, ty = int(x * self.factor), int(y * self.factor)
        return 0 <= tx < w and 0 <= ty < self._h and self.background[ty * w + tx] == 1

    _h: int = 1  # the traced picture's height
    nodes: int = 0  # the points its outlines go through (export.node_count)


_SIZE = re.compile(r'<svg ([^>]*?)width="\d+" height="\d+"')


def set_size(svg, width, height):
    """Give the SVG <width> x <height> (its viewBox, the traced pixels, stays)."""
    return _SIZE.sub(lambda m: '<svg %swidth="%d" height="%d"' % (m.group(1), width, height), svg, count=1)


FADE = 0.75  # how far the other colors go toward white


def marked(svg, colors):
    """The SVG with every color but these ((r, g, b) each) faded toward white, everything in its
    place: the window marks the selected colors with it. (Drawing only the selected colors over
    a faded SVG was wrong with Stack: a color's shape also covers the colors stacked on it.) The
    engine writes each run of a color as a group of its own, <g id="color-rrggbb">, its shapes in
    that color: its groups found and replaced in with plain string steps (a regular expression
    took 0.19 s for a photo's 23 MB SVG)."""
    wanted = {"%02x%02x%02x" % tuple(c) for c in colors}
    out = []
    at = 0
    head = '<g id="color-'
    while True:
        start = svg.find(head, at)
        if start < 0:
            break
        end = svg.find("</g>", start)
        if end < 0:
            break
        end += 4
        hexa = svg[start + len(head):start + len(head) + 6]
        if hexa not in wanted and re.fullmatch("[0-9a-f]{6}", hexa):
            v = int(hexa, 16)
            faded = "%02x%02x%02x" % tuple(round(c + (255 - c) * FADE)
                                           for c in ((v >> 16) & 255, (v >> 8) & 255, v & 255))
            out.append(svg[at:start])
            out.append(svg[start:end].replace("#" + hexa, "#" + faded))
            at = end
        else:
            out.append(svg[at:end])
            at = end
    out.append(svg[at:])
    return "".join(out)


def _stamp(svg):
    """The program's version in the SVG's "Created with" note (the engine writes its own)."""
    from kanzonassvg import __version__
    return svg.replace("<!-- Created with KanzonasSVG %s -->" % engine.version(),
                       "<!-- Created with KanzonasSVG %s -->" % __version__, 1)


def trace_image(img, options, enlarge=AUTO, progress=None):
    """Trace a QImage (RGBA8888). The SVG has the picture's own size."""
    t = time.perf_counter()
    factor = enlarge_factor(enlarge, img.width(), img.height())
    if options.mode in (engine.AUTOTRACE, engine.CENTERLINE) and max(img.width(), img.height()) > AUTOTRACE_MAX_SIDE:
        raise engine.TraceError(tr("Autotrace traces pictures up to 65,535 pixels wide and high; this one "
                                   "is %d x %d pixels. Pick Colors or another mode that isn't Autotrace.")
                                % (img.width(), img.height()))
    work = image.scaled(img, factor)
    data, w, h, stride = image.pixels(work)
    svg, n = engine.trace(data, w, h, stride, options, progress)
    svg = _stamp(svg)
    if factor != 1:
        svg = set_size(svg, img.width(), img.height())
    # (the engine kept the colors it just traced with: quick)
    colors, region = engine.palette(data, w, h, stride, options, mask=True) if options.mode in COLOR_MODES \
        else (None, None)
    return Result(svg, n, time.perf_counter() - t, factor, colors, region, h, export.node_count(svg))


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
    return set_size(_stamp(svg), w, h)


def preview_image(img, options):
    """The picture as it will be traced (colors reduced), as a QImage."""
    from PySide6.QtGui import QImage

    data, w, h, stride = image.pixels(img)
    rgb = engine.preview(data, w, h, stride, options)
    return QImage(rgb, w, h, w * 3, QImage.Format.Format_RGB888).copy()
