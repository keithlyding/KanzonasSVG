"""Draw the app icon: assets/kanzonassvg.png (256 px) and assets/kanzonassvg.ico (16-256 px).

    python tools/make_icon.py

A plain placeholder (a curve with its nodes and handles), not a Kanzonas logo: logos come
from the Kanzonas-Site repository's brand/ folder.
"""

import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def draw(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)
    g = QLinearGradient(0, 0, 0, 256)
    g.setColorAt(0, QColor("#2b6cb0"))
    g.setColorAt(1, QColor("#1a3f7a"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 44, 44)
    a, c1, c2, b = QPointF(52, 186), QPointF(70, 60), QPointF(186, 210), QPointF(204, 74)
    p.setPen(QPen(QColor(255, 255, 255, 150), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(a, c1)
    p.drawLine(b, c2)
    path = QPainterPath(a)
    path.cubicTo(c1, c2, b)
    p.setPen(QPen(QColor("#ffffff"), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffd23f"))
    for pt in (a, b):
        p.drawRect(QRectF(pt.x() - 15, pt.y() - 15, 30, 30))
    p.setBrush(QColor("#ffffff"))
    for pt in (c1, c2):
        p.drawEllipse(pt, 12, 12)
    p.end()
    return img


def png_bytes(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def main():
    if QGuiApplication.instance() is None:
        main.app = QGuiApplication(sys.argv[:1])
    out = os.path.join(ROOT, "assets")
    os.makedirs(out, exist_ok=True)
    draw(256).save(os.path.join(out, "kanzonassvg.png"))
    draw(128).save(os.path.join(ROOT, "kanzonassvg", "icon.png"))  # the window icon
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [png_bytes(draw(s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    with open(os.path.join(out, "kanzonassvg.ico"), "wb") as f:
        f.write(header + entries + b"".join(images))
    print("assets/kanzonassvg.png, assets/kanzonassvg.ico")


if __name__ == "__main__":
    main()
