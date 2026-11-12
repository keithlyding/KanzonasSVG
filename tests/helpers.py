"""Pictures to trace, and drawing an SVG back into pixels to check it."""

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer

from kanzonassvg import image

RED = QColor(0xB2, 0x00, 0x2D)
BLUE = QColor(0x1D, 0x3F, 0x8F)


def canvas(w, h, color=Qt.GlobalColor.white):
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(color)
    return img


def logo(w=240, h=160, antialias=True):
    """White, a red block, and a blue ring with a blue dot inside (an O around a dot)."""
    img = canvas(w, h)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
    p.fillRect(QRectF(20, 30, 70, 100), RED)
    p.setPen(QPen(BLUE, 16))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(165, 80), 50, 50)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BLUE)
    p.drawEllipse(QPointF(165, 80), 12, 12)
    p.end()
    return image.to_rgba(img)


def render(svg, w, h):
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    assert r.isValid(), "not a valid SVG"
    out = QImage(w, h, QImage.Format.Format_RGBA8888)
    out.fill(Qt.GlobalColor.white)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, w, h))
    p.end()
    return out


def color_at(img, x, y):
    c = img.pixelColor(x, y)
    return c.red(), c.green(), c.blue()


def close(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def bad_pixels(a, b, tol=64):
    """Fraction of pixels off by more than <tol> levels in some channel."""
    w, h = a.width(), a.height()
    bad = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if not close(color_at(a, x, y), color_at(b, x, y), tol):
                bad += 1
    return bad / ((w // 2) * (h // 2))
