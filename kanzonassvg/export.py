"""Saving the trace as SVG, PDF, EPS or DXF, at a size of the user's choosing.

Everything here starts from the SVG the engine wrote (tracing.Result.svg): its <path>s, each
with one color ("fill:#rrggbb" or "stroke:#rrggbb") and a path of absolute M, L, C and Z, in
the units of its viewBox (the traced pixels), and the size the picture had (width/height).

Sizes: a picture's pixel counts as 1/96 inch (CSS, browsers, Inkscape, Illustrator), unless a
width in inches or millimeters is asked for (Size); the height follows.

- SVG: the same, with width and height in in/mm when a size is asked for.
- PDF and EPS: one page that size, the shapes in their colors (their path numbers copied as
  they are, under a scale: exact, and quick).
- DXF (R12, read by nearly every CAD, laser and cutting program): each shape's outlines as
  polylines (curves as short straight pieces, within 0.025 mm), one layer for each color, named
  by it (COLOR_FF0000) and drawn in the nearest AutoCAD color. In millimeters, or in inches
  when the size is asked for in inches: R12 can't say which, so a program may ask.
"""

import math
import os
import re
import zlib
from dataclasses import dataclass

from kanzonassvg import __version__

PX, IN, MM = "px", "in", "mm"
UNITS = (PX, IN, MM)
MM_PER_IN = 25.4
PX_PER_IN = 96.0
PT_PER_IN = 72.0

FORMATS = ("svg", "pdf", "eps", "dxf")
FILTERS = {
    "svg": "SVG (*.svg)",
    "pdf": "PDF (*.pdf)",
    "eps": "EPS (*.eps)",
    "dxf": "DXF for CAD, laser and cutting programs (*.dxf)",
}


@dataclass(frozen=True)
class Size:
    """The saved width: <width> in <unit>, or the picture's own pixels (unit PX)."""

    unit: str = PX
    width: float = 0.0

    def __post_init__(self):
        if self.unit not in UNITS:
            raise ValueError("unit must be one of %s" % ", ".join(UNITS))
        if self.unit != PX and not (self.width > 0 and math.isfinite(self.width)):
            raise ValueError("the width must be more than 0")


PIXELS = Size()


def format_of(path, default="svg"):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext if ext in FORMATS else default


# reading the engine's SVG

_ROOT = re.compile(r'<svg [^>]*?width="([\d.]+)[a-z]*" height="([\d.]+)[a-z]*" viewBox="0 0 ([\d.]+) ([\d.]+)"')
_PATH = re.compile(r'<path style="([^"]*)" d="([^"]*)"')
_STEP = re.compile(r"([MLCZ])([^MLCZ]*)")


def svg_size(svg):
    """(width, height, viewBox width, viewBox height) of the engine's SVG: the size in pixels
    it shows at and the units its paths are in."""
    m = _ROOT.search(svg)
    if not m:
        raise ValueError("not an SVG KanzonasSVG wrote")
    w, h, vw, vh = (float(v) for v in m.groups())
    return w, h, max(vw, 1e-9), max(vh, 1e-9)


def inches(svg, size=PIXELS):
    """The saved page's (width, height) in inches."""
    w, h = svg_size(svg)[:2]
    if size.unit == PX:
        return w / PX_PER_IN, h / PX_PER_IN
    wi = size.width / MM_PER_IN if size.unit == MM else size.width
    return wi, wi * h / max(w, 1e-9)


def size_text(svg, size=PIXELS):
    """The saved size, as the window says it ("1280 x 960 pixels (13.33 x 10 in)", "4 x 3 in")."""
    w, h = svg_size(svg)[:2]
    wi, hi = inches(svg, size)
    if size.unit == PX:
        return "%d x %d pixels (%s x %s in)" % (round(w), round(h), _short(wi), _short(hi))
    k = MM_PER_IN if size.unit == MM else 1.0
    return "%s x %s %s" % (_short(wi * k), _short(hi * k), size.unit)


def _short(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def shapes(svg):
    """[(stroke?, (r, g, b), d)] bottom up."""
    out = []
    for style, d in _PATH.findall(svg):
        stroke = style.startswith("fill:none")
        m = re.search(r"(?:fill|stroke):#([0-9a-fA-F]{6})", style if not stroke else style[len("fill:none"):])
        if not m:
            continue
        v = int(m.group(1), 16)
        out.append((stroke, (v >> 16, v >> 8 & 255, v & 255), d))
    return out


def node_count(svg):
    """The points the SVG's outlines go through (where a cutting machine turns: fewer cut cleaner)."""
    return sum(d.count("M") + d.count("L") + d.count("C") for _s, _c, d in shapes(svg))


def _numbers(text):
    return text.replace(",", " ").split()


# SVG

_SIZE_ATTRS = re.compile(r'(<svg [^>]*?)width="[^"]*" height="[^"]*"')


def sized_svg(svg, size=PIXELS):
    if size.unit == PX:
        return svg
    wi, hi = inches(svg, size)
    k = MM_PER_IN if size.unit == MM else 1.0
    return _SIZE_ATTRS.sub(lambda m: '%swidth="%s%s" height="%s%s"' % (
        m.group(1), _num(wi * k), size.unit, _num(hi * k), size.unit), svg, count=1)


def _num(v):
    """A number with up to 4 decimals and a '.' (whatever the locale: % formatting ignores it)."""
    s = "%.4f" % v
    return s.rstrip("0").rstrip(".") if "." in s else s


# PDF and EPS: the path numbers as they are, under a scale (pt per viewBox unit, y down)

def _ops(d, move, line, curve, close):
    out = []
    for cmd, args in _STEP.findall(d):
        if cmd == "Z":
            out.append(close)
            continue
        n = _numbers(args)
        op = {"M": move, "L": line, "C": curve}[cmd]
        step = 6 if cmd == "C" else 2
        for i in range(0, len(n) - step + 1, step):
            out.append(" ".join(n[i:i + step]) + " " + op)
    return out


def _rgb(c):
    return " ".join(_num(v / 255.0) for v in c)


def _page(svg, size):
    wi, hi = inches(svg, size)
    W, H = wi * PT_PER_IN, hi * PT_PER_IN
    vw, vh = svg_size(svg)[2:]
    return W, H, W / vw, H / vh


def to_pdf(svg, size=PIXELS):
    W, H, sx, sy = _page(svg, size)
    body = ["q", "%s 0 0 %s 0 %s cm" % (_num(sx), _num(-sy), _num(H)), "1 j 1 J"]
    for stroke, color, d in shapes(svg):
        body.append(_rgb(color) + (" RG 1 w" if stroke else " rg"))
        body.extend(_ops(d, "m", "l", "c", "h"))
        body.append("S" if stroke else "f")
    body.append("Q")
    stream = zlib.compress(("\n".join(body) + "\n").encode("ascii"), 6)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Resources << >> /Contents 4 0 R >>"
         % (_num(W), _num(H))).encode("ascii"),
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream",
        ("<< /Producer (KanzonasSVG %s) /Creator (KanzonasSVG %s) >>" % (__version__, __version__)).encode("ascii"),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body_bytes in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for o in offsets:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, len(objects), xref)
    return bytes(out)


def to_eps(svg, size=PIXELS):
    W, H, sx, sy = _page(svg, size)
    lines = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        "%%%%BoundingBox: 0 0 %d %d" % (math.ceil(W), math.ceil(H)),
        "%%%%HiResBoundingBox: 0 0 %s %s" % (_num(W), _num(H)),
        "%%%%Creator: KanzonasSVG %s" % __version__,
        "%%LanguageLevel: 2",
        "%%Pages: 1",
        "%%EndComments",
        "%%BeginProlog",
        "/m {moveto} bind def /l {lineto} bind def /c {curveto} bind def /h {closepath} bind def",
        "%%EndProlog",
        "%%Page: 1 1",
        "gsave",
        "0 %s translate %s %s scale 1 setlinejoin 1 setlinecap" % (_num(H), _num(sx), _num(-sy)),
    ]
    for stroke, color, d in shapes(svg):
        lines.append("newpath " + _rgb(color) + " setrgbcolor" + (" 1 setlinewidth" if stroke else ""))
        lines.extend(_ops(d, "m", "l", "c", "h"))
        lines.append("stroke" if stroke else "fill")
    lines += ["grestore", "showpage", "%%EOF", ""]
    return "\n".join(lines).encode("ascii")


# DXF (R12)

# AutoCAD's 256 standard colors (ACI: index 0 to 255), as ezdxf has them
# (ezdxf.colors.DXF_DEFAULT_COLORS; tests/test_export.py checks them against it)
_ACI_HEX = (
    "000000ff0000ffff0000ff0000ffff0000ffff00ffffffff808080c0c0c0ff0000ff7f7fa50000a552527f00007f3f3f"
    "4c00004c2626260000261313ff3f00ff9f7fa52900a567527f1f007f4f3f4c13004c2f26260900261713ff7f00ffbf7f"
    "a55200a57c527f3f007f5f3f4c26004c3926261300261c13ffbf00ffdf7fa57c00a591527f5f007f6f3f4c39004c4226"
    "261c00262113ffff00ffff7fa5a500a5a5527f7f007f7f3f4c4c004c4c26262600262613bfff00dfff7f7ca50091a552"
    "5f7f006f7f3f394c00424c261c26002126137fff00bfff7f52a5007ca5523f7f005f7f3f264c00394c261326001c2613"
    "3fff009fff7f29a50067a5521f7f004f7f3f134c002f4c2609260017261300ff007fff7f00a50052a552007f003f7f3f"
    "004c00264c2600260013261300ff3f7fff9f00a52952a567007f1f3f7f4f004c13264c2f00260913581700ff7f7fffbf"
    "00a55252a57c007f3f3f7f5f004c26264c3900261313581c00ffbf7fffdf00a57c52a591007f5f3f7f6f004c39264c42"
    "00261c13585800ffff7fffff00a5a552a5a5007f7f3f7f7f004c4c264c4c00262613585800bfff7fdfff007ca55291a5"
    "005f7f3f6f7f00394c26427e001c26135858007fff7fbfff0052a5527ca5003f7f3f5f7f00264c26397e001326131c58"
    "003fff7f9fff0029a55267a5001f7f3f4f7f00134c262f7e0009261317580000ff7f7fff0000a55252a500007f3f3f7f"
    "00004c26267e0000261313583f00ff9f7fff2900a56752a51f007f4f3f7f13004c2f267e0900261713587f00ffbf7fff"
    "5200a57c52a53f007f5f3f7f26004c39267e1300261c1358bf00ffdf7fff7c00a59152a55f007f6f3f7f39004c42264c"
    "1c0026581358ff00ffff7fffa500a5a552a57f007f7f3f7f4c004c4c264c260026581358ff00bfff7fdfa5007ca55291"
    "7f005f7f3f6f4c00394c264226001c581358ff007fff7fbfa50052a5527c7f003f7f3f5f4c00264c263926001358131c"
    "ff003fff7f9fa50029a552677f001f7f3f4f4c00134c262f260009581317000000656565666666999999ccccccffffff"
)


def _aci_table():
    """[(index, (r, g, b))] of the 255 colors a layer can have (1-255)."""
    raw = bytes.fromhex(_ACI_HEX)
    return [(i, (raw[3 * i], raw[3 * i + 1], raw[3 * i + 2])) for i in range(1, 256)]


def nearest_aci(rgb, table=None):
    table = table or _aci_table()
    return min(table, key=lambda t: sum((a - b) ** 2 for a, b in zip(t[1], rgb)))[0]


def _flatten(d, scale, tolerance):
    """[(closed?, [(x, y)])]: the path's pieces in output units (y up), curves as straight
    pieces within <tolerance> of them."""
    pieces, pts = [], None
    sx, sy, H = scale
    x = y = x0 = y0 = 0.0
    for cmd, args in _STEP.findall(d):
        if cmd == "Z":
            if pts and len(pts) > 1:
                pieces.append((True, pts))
            pts, x, y = None, x0, y0                        # (after Z: back at the piece's start)
            continue
        n = [float(v) for v in _numbers(args)]
        if pts is None and cmd != "M":                      # (a step after Z without M: from there)
            pts = [(x * sx, H - y * sy)]
        if cmd == "M":
            if pts and len(pts) > 1:
                pieces.append((False, pts))
            x, y = x0, y0 = n[0], n[1]
            pts = [(x * sx, H - y * sy)]
            for i in range(2, len(n) - 1, 2):            # (an M with more points: lines)
                x, y = n[i], n[i + 1]
                pts.append((x * sx, H - y * sy))
        elif cmd == "L":
            for i in range(0, len(n) - 1, 2):
                x, y = n[i], n[i + 1]
                pts.append((x * sx, H - y * sy))
        else:
            for i in range(0, len(n) - 5, 6):
                p0 = (x * sx, H - y * sy)
                p1 = (n[i] * sx, H - n[i + 1] * sy)
                p2 = (n[i + 2] * sx, H - n[i + 3] * sy)
                p3 = (n[i + 4] * sx, H - n[i + 5] * sy)
                # how far uniform pieces can stray: 3/4 of the biggest second difference / pieces^2
                dd = max(math.hypot(p0[0] - 2 * p1[0] + p2[0], p0[1] - 2 * p1[1] + p2[1]),
                         math.hypot(p1[0] - 2 * p2[0] + p3[0], p1[1] - 2 * p2[1] + p3[1]))
                k = max(1, min(200, math.ceil(math.sqrt(0.75 * dd / tolerance))))
                for j in range(1, k + 1):
                    t = j / k
                    u = 1 - t
                    a, b, c, e = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
                    pts.append((a * p0[0] + b * p1[0] + c * p2[0] + e * p3[0],
                                a * p0[1] + b * p1[1] + c * p2[1] + e * p3[1]))
                x, y = n[i + 4], n[i + 5]
    if pts and len(pts) > 1:
        pieces.append((False, pts))
    for closed, p in pieces:
        if closed and len(p) > 2 and math.hypot(p[0][0] - p[-1][0], p[0][1] - p[-1][1]) < tolerance / 10:
            p.pop()                                         # (closed: the last point is the first)
    return pieces


def to_dxf(svg, size=PIXELS):
    wi, hi = inches(svg, size)
    k = 1.0 if size.unit == IN else MM_PER_IN               # output units per inch
    W, H = wi * k, hi * k
    vw, vh = svg_size(svg)[2:]
    tolerance = 0.025 if size.unit != IN else 0.025 / MM_PER_IN
    table = _aci_table()
    found = shapes(svg)
    layers = {}
    for _stroke, color, _d in found:
        layers.setdefault(color, "COLOR_%02X%02X%02X" % color)
    out = []

    def g(code, value):
        out.append("%3d\n%s\n" % (code, value))

    g(0, "SECTION"), g(2, "HEADER")
    g(9, "$ACADVER"), g(1, "AC1009")
    g(9, "$INSBASE"), g(10, "0.0"), g(20, "0.0"), g(30, "0.0")
    g(9, "$EXTMIN"), g(10, "0.0"), g(20, "0.0"), g(30, "0.0")
    g(9, "$EXTMAX"), g(10, _num(W)), g(20, _num(H)), g(30, "0.0")
    g(9, "$LIMMIN"), g(10, "0.0"), g(20, "0.0")
    g(9, "$LIMMAX"), g(10, _num(W)), g(20, _num(H))
    g(0, "ENDSEC")
    g(0, "SECTION"), g(2, "TABLES")
    g(0, "TABLE"), g(2, "LTYPE"), g(70, 1)
    g(0, "LTYPE"), g(2, "CONTINUOUS"), g(70, 0), g(3, "Solid line"), g(72, 65), g(73, 0), g(40, "0.0")
    g(0, "ENDTAB")
    g(0, "TABLE"), g(2, "LAYER"), g(70, len(layers) + 1)
    g(0, "LAYER"), g(2, "0"), g(70, 0), g(62, 7), g(6, "CONTINUOUS")
    for color, name in layers.items():
        g(0, "LAYER"), g(2, name), g(70, 0), g(62, nearest_aci(color, table)), g(6, "CONTINUOUS")
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"), g(2, "ENTITIES")
    scale = (W / vw, H / vh, H)
    for _stroke, color, d in found:
        layer = layers[color]
        for closed, pts in _flatten(d, scale, tolerance):
            g(0, "POLYLINE"), g(8, layer), g(66, 1), g(10, "0.0"), g(20, "0.0"), g(30, "0.0"), g(70, 1 if closed else 0)
            for x, y in pts:
                g(0, "VERTEX"), g(8, layer), g(10, "%.3f" % x), g(20, "%.3f" % y), g(30, "0.0")
            g(0, "SEQEND"), g(8, layer)
    g(0, "ENDSEC")
    g(0, "EOF")
    return "".join(out)


# saving

def render(svg, fmt, size=PIXELS):
    """The file's bytes."""
    if fmt == "svg":
        return sized_svg(svg, size).encode("utf-8")
    if fmt == "pdf":
        return to_pdf(svg, size)
    if fmt == "eps":
        return to_eps(svg, size)
    if fmt == "dxf":
        return to_dxf(svg, size).encode("ascii")
    raise ValueError("unknown format: %s" % fmt)


def write(path, svg, fmt=None, size=PIXELS):
    """Save it (all or nothing: a .part file renamed when done)."""
    data = render(svg, fmt or format_of(path), size)
    tmp = path + ".part"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
