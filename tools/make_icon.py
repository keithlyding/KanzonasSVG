"""Draw KanzonasSVG's icons from the owner's artwork (the cactus and sunflower).

    QT_QPA_PLATFORM=offscreen python tools/make_icon.py

Needs numpy, Pillow and the Inter font (build time only; the outputs are in the repository).

The same design as KanzonasPDF's icon (its tools_make_assets.py, which this follows step for
step, so the two match letter for letter): a rounded tile, the owner's cactus and sunflower
(assets/kanzonas-mark-source.png, unchanged from KanzonasPDF) in front of a page, and a white
tag across the bottom with the program's name. KanzonasSVG's: an orange tile, "SVG" on the tag
in the same orange, and on the page a curve with its nodes and handles (a vector drawing)
instead of lines of writing. The installer's icon is the same on a blue tile, with the "SVG"
letters still orange.

Outputs: assets/kanzonassvg.png (256 px), assets/kanzonassvg.ico (app, 16-256 px),
assets/kanzonassvg-setup.ico (installer), assets/wizard-large.bmp and wizard-small.bmp (the
installer's pages), kanzonassvg/icon.png (the window's icon, 256 px).

This is an icon, not a logo: Kanzonas logos (the wordmark) come only from the Kanzonas-Site
repository's brand/ folder.
"""
import io
import os
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv[:1])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mark = QImage(os.path.join(ROOT, "assets", "kanzonas-mark-source.png"))
if mark.isNull():
    sys.exit("assets/kanzonas-mark-source.png is missing")


# The app's color: orange (KanzonasPDF is red, KanzonasCAD purple). The tile and the "SVG"
# letters are this color; the installer's icon has the same letters on a blue tile, as
# KanzonasPDF's installer does, so the setup file can't be taken for the program itself.
ORANGE_TOP, ORANGE_BOTTOM = "#ef7d00", "#b34f00"
BLUE_TOP, BLUE_BOTTOM = "#2b88e8", "#0a4ea8"
TILE = [ORANGE_TOP, ORANGE_BOTTOM]


MARGIN = 3.0      # gap (in tile units of 256) kept between the artwork and the tile's edge

# the tag (tile units of 256, measured on KanzonasCAD's icon so the two match)
LABEL = "SVG"
LABEL_COLOR = ORANGE_TOP                    # the app's orange at the top of the letters (on both icons)
LABEL_COLOR_BOTTOM = ORANGE_BOTTOM          # shading to this at the bottom
LABEL_FONT = "Inter"
ART_SCALE, ART_PIVOT = 0.878, (85.7, 22.1)  # the art 12% smaller, toward the top
TAG_RECT = (58.25, 162.5, 187.75, 81.75)    # outer: x, y, width, height
TAG_BORDER, TAG_RADIUS = 3.5, 11.0
TAG_BORDER_COLOR = "#0a100e"
CAP_TOP, CAP_BOTTOM = 167.75, 239.75        # the letters' top and bottom
LABEL_SQUEEZE = 0.783                       # width / height scale of the letters


def _tile(p, size_units, radius):
    g = QLinearGradient(0, 0, size_units * 0.35, size_units)     # light top left, deep bottom
    g.setColorAt(0, QColor(TILE[0]))
    g.setColorAt(1, QColor(TILE[1]))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    m = size_units / 64
    p.drawRoundedRect(QRectF(m, m, size_units - 2 * m, size_units - 2 * m), radius, radius)


def _page(p, x0, y0, x1, y1, f, line=True):
    """White page with a folded top-right corner (as in the owner's artwork)."""
    page = QPainterPath()
    r = (x1 - x0) * 0.07
    page.moveTo(x0 + r, y0)
    page.lineTo(x1 - f, y0)
    page.lineTo(x1, y0 + f)
    page.lineTo(x1, y1 - r)
    page.quadTo(x1, y1, x1 - r, y1)
    page.lineTo(x0 + r, y1)
    page.quadTo(x0, y1, x0, y1 - r)
    page.lineTo(x0, y0 + r)
    page.quadTo(x0, y0, x0 + r, y0)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 60))                    # soft shadow
    p.drawPath(page.translated((x1 - x0) * 0.02, (x1 - x0) * 0.025))
    p.setBrush(QColor("white"))
    if line:
        p.setPen(QPen(QColor("#5a5a5a"), (x1 - x0) * 0.035))
    p.drawPath(page)
    fold = QPainterPath()
    fold.moveTo(x1 - f, y0)
    fold.lineTo(x1 - f, y0 + f)
    fold.lineTo(x1, y0 + f)
    fold.closeSubpath()
    p.setBrush(QColor("#d9d9d9"))
    p.drawPath(fold)
    # a curve with its nodes and handles: a vector drawing, as an SVG holds
    w = x1 - x0
    lw = w * (0.035 if line else 0.06)
    ax, ay = x0 + w * 0.16, y0 + w * 0.62
    bx, by = x1 - w * 0.16, y0 + w * 0.30
    c1 = QPointF(x0 + w * 0.30, y0 + w * 0.12)
    c2 = QPointF(x1 - w * 0.34, y0 + w * 0.86)
    if line:
        hp = QPen(QColor("#9a9a9a"), lw * 0.6)
        p.setPen(hp)
        p.drawLine(QPointF(ax, ay), c1)
        p.drawLine(QPointF(bx, by), c2)
    curve = QPainterPath(QPointF(ax, ay))
    curve.cubicTo(c1, c2, QPointF(bx, by))
    pen = QPen(QColor("#5f6b78"), lw * 1.6)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(curve)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#5f6b78"))
    n = w * (0.09 if line else 0.12)
    for (nx, ny) in ((ax, ay), (bx, by)):
        p.drawRect(QRectF(nx - n / 2, ny - n / 2, n, n))
    if line:
        p.setBrush(QColor("#9a9a9a"))
        for c in (c1, c2):
            p.drawEllipse(c, n * 0.4, n * 0.4)


def _fading_page(p, units, x0, y0, x1, y1, f, line=True, fade_from=0.1, fade_to=1.0):
    """The page drawn on its own layer: white at the top, shading to transparent at the
    bottom, so it seems to come out from behind the cactus."""
    layer = QImage(p.device().width(), p.device().height(), QImage.Format_ARGB32_Premultiplied)
    layer.fill(Qt.transparent)
    q = QPainter(layer)
    q.setRenderHint(QPainter.Antialiasing)
    q.setTransform(p.transform())       # same scale (and enlargement) as the icon
    _page(q, x0, y0, x1, y1, f, line)
    q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    g = QLinearGradient(0, y0 + (y1 - y0) * fade_from, 0, y0 + (y1 - y0) * fade_to)
    g.setColorAt(0, QColor(0, 0, 0, 255))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    q.fillRect(QRectF(-units, -units, 3 * units, 3 * units), g)
    q.end()
    p.save()
    p.resetTransform()
    p.drawImage(0, 0, layer)
    p.restore()


def _outlined(p, r, width):
    """The owner's cactus and sunflower with a white outline around them."""
    import math
    sil = mark.copy()
    q = QPainter(sil)
    q.setCompositionMode(QPainter.CompositionMode_SourceIn)
    q.fillRect(sil.rect(), QColor("white"))
    q.end()
    for k in range(24):
        a = 2 * math.pi * k / 24
        p.drawImage(r.translated(width * math.cos(a), width * math.sin(a)), sil)
    p.drawImage(r, mark)


def _big_mark_rect():
    h = 178.0
    w = h * mark.width() / mark.height()
    return QRectF(128 - w / 2, 58, w, h)


def _small_mark_rect():
    h = 96.0
    w = h * mark.width() / mark.height()
    return QRectF(64 - w / 2, 28, w, h)


def _big_art(p):
    _fading_page(p, 256, 84, 62, 202, 224, 28)
    _outlined(p, _big_mark_rect(), 3.0)


def _small_art(p):
    _fading_page(p, 128, 39, 31, 103, 115, 16, line=False)
    _outlined(p, _small_mark_rect(), 2.2)


def _flower_only():
    """The sunflower alone (its petals, center and their dark outlines), to draw over the
    tag where it overlaps the tag's top."""
    import numpy as np
    img = mark.convertToFormat(QImage.Format_RGBA8888)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.width(), 4).copy()
    r, g, b, al = (a[..., i].astype(int) for i in range(4))
    op = al > 128
    yellow = op & (r > 180) & (g > 110) & (b < 110)
    brown = op & (r > 70) & (r < 200) & (g < 120) & (b < 80) & (r > g + 25)
    keep = yellow | brown
    for _ in range(3):                          # (the petals' dark outlines too)
        grown = keep.copy()
        grown[1:] |= keep[:-1]
        grown[:-1] |= keep[1:]
        grown[:, 1:] |= keep[:, :-1]
        grown[:, :-1] |= keep[:, 1:]
        keep = grown
    a[..., 3] = np.where(keep, a[..., 3], 0)
    return QImage(a.tobytes(), img.width(), img.height(), img.width() * 4,
                  QImage.Format_RGBA8888).copy()


flower = _flower_only()


def _big_flower(p):
    p.drawImage(_big_mark_rect(), flower)


def _small_flower(p):
    p.drawImage(_small_mark_rect(), flower)


def _tag(p, units):
    """The white tag with LABEL across the bottom of the tile (tile units of `units`)."""
    from PySide6.QtGui import QFont, QFontDatabase
    k = units / 256
    x, y, w, h = (v * k for v in TAG_RECT)
    outer = QRectF(x, y, w, h)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(TAG_BORDER_COLOR))
    p.drawRoundedRect(outer, TAG_RADIUS * k, TAG_RADIUS * k)
    b = TAG_BORDER * k
    p.setBrush(QColor("white"))
    p.drawRoundedRect(outer.adjusted(b, b, -b, -b), (TAG_RADIUS - TAG_BORDER) * k,
                      (TAG_RADIUS - TAG_BORDER) * k)
    if LABEL_FONT not in QFontDatabase.families():
        print(f"warning: the {LABEL_FONT} font isn't installed: the tag's letters will differ")
    f = QFont(LABEL_FONT)
    f.setPixelSize(400)
    f.setWeight(QFont.Black)
    path = QPainterPath()
    path.addText(0, 0, f, LABEL)
    box = path.boundingRect()
    sy = (CAP_BOTTOM - CAP_TOP) * k / box.height()
    sx = sy * LABEL_SQUEEZE
    p.save()
    p.translate(x + w / 2 - box.width() * sx / 2, CAP_TOP * k)
    p.scale(sx, sy)
    p.translate(-box.x(), -box.y())
    shade = QLinearGradient(0, box.y(), 0, box.y() + box.height())
    shade.setColorAt(0, QColor(LABEL_COLOR))
    shade.setColorAt(1, QColor(LABEL_COLOR_BOTTOM))
    p.setBrush(shade)
    p.drawPath(path)
    p.restore()


def _render(size, units, transform, art):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(size / units, size / units)
    if transform:
        transform(p)
    art(p)
    p.end()
    return img


def _fit(units, radius, art, size=512):
    """The largest enlargement of the page and cactus, centered in the tile, that stays
    inside the rounded tile (MARGIN units from its edge). Returns a function that applies
    it to a painter."""
    import numpy as np
    k = size / units

    def alpha(img):
        a = np.frombuffer(img.constBits(), np.uint8).reshape(size, size, 4)[:, :, 3]
        return a > 24
    ys, xs = np.nonzero(alpha(_render(size, units, None, art)))
    cx, cy = (xs.min() + xs.max() + 1) / 2 / k, (ys.min() + ys.max() + 1) / 2 / k
    m = units / 64 + MARGIN * units / 256
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(m, m, units - 2 * m, units - 2 * m), radius, radius)
    inside = np.zeros((size, size), bool)
    for y in range(size):
        for x in range(size):
            inside[y, x] = tile.contains(QPointF((x + 0.5) / k, (y + 0.5) / k))

    def make(s):
        def apply(p):
            p.translate(units / 2, units / 2)
            p.scale(s, s)
            p.translate(-cx, -cy)
        return apply
    lo, hi = 1.0, 2.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if (alpha(_render(size, units, make(mid), art)) & ~inside).any():
            hi = mid
        else:
            lo = mid
    print(f"artwork enlarged {lo:.3f}x")
    return make(lo)


def _icon(size, units, radius, art, flower_art=None):
    fit = _fit(units, radius, art)
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(size / units, size / units)
    _tile(p, units, radius)

    def placed():
        if LABEL:                       # (smaller and higher, above the tag)
            k = units / 256
            px, py = ART_PIVOT[0] * k, ART_PIVOT[1] * k
            p.translate(px, py)
            p.scale(ART_SCALE, ART_SCALE)
            p.translate(-px, -py)
        fit(p)
    p.save()
    placed()
    art(p)
    p.restore()
    if LABEL:
        _tag(p, units)
        if flower_art is not None:      # the sunflower just over the tag's top
            p.save()
            placed()
            flower_art(p)
            p.restore()
    p.end()
    return img


def big_icon(size=512):
    """Orange tile; the owner's cactus and sunflower stand in front of a white page whose top
    comes out above the cactus, as big as fits inside the tile."""
    return _icon(size, 256, 44, _big_art, _big_flower)


def small_icon(size=128):
    """16-32 px: same layout, bolder and simpler (no page outline)."""
    return _icon(size, 128, 24, _small_art, _small_flower)


def to_pil(qimg):
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    qimg.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")




def write(name, big, small, sizes):
    frames = {s: (small if s <= 32 else big).resize((s, s), Image.LANCZOS) for s in sizes}
    frames[sizes[-1]].save(os.path.join(ROOT, "assets", name), sizes=[(s, s) for s in sizes],
                           append_images=[frames[s] for s in sizes[:-1]])
    return frames


def on_white(img, w, h, size, pos):
    bg = Image.new("RGB", (w, h), "white")
    im = img.resize((size, size), Image.LANCZOS)
    bg.paste(im, pos, im)
    return bg


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big, small = to_pil(big_icon()), to_pil(small_icon())
    frames = write("kanzonassvg.ico", big, small, sizes)
    frames[256].save(os.path.join(ROOT, "assets", "kanzonassvg.png"))
    frames[256].save(os.path.join(ROOT, "kanzonassvg", "icon.png"))
    TILE[:] = [BLUE_TOP, BLUE_BOTTOM]           # installer: blue tile, same orange letters
    setup_big, setup_small = to_pil(big_icon()), to_pil(small_icon())
    TILE[:] = [ORANGE_TOP, ORANGE_BOTTOM]
    write("kanzonassvg-setup.ico", setup_big, setup_small, sizes)
    on_white(setup_big, 164, 314, 150, (7, 80)).save(os.path.join(ROOT, "assets", "wizard-large.bmp"))
    on_white(setup_big, 55, 55, 51, (2, 2)).save(os.path.join(ROOT, "assets", "wizard-small.bmp"))
    print("icons written")


if __name__ == "__main__":
    main()
