"""The tracing engine (core/, a C library) through ctypes.

The engine is Inkscape's Trace Bitmap (Potrace and Autotrace) with KanzonasSVG's
quality and speed fixes; see core/src/kzsvg.h for the interface.
"""

import ctypes
import os
import sys
from dataclasses import dataclass, fields

# Modes (enum kz_mode in kzsvg.h)
COLORS = 0
GRAYS = 1
BRIGHTNESS_STEPS = 2
BRIGHTNESS = 3
EDGES = 4
AUTOTRACE = 5
CENTERLINE = 6

MODE_NAMES = {
    COLORS: "colors",
    GRAYS: "grays",
    BRIGHTNESS_STEPS: "steps",
    BRIGHTNESS: "bw",
    EDGES: "edges",
    AUTOTRACE: "autotrace",
    CENTERLINE: "centerline",
}
MODES_BY_NAME = {v: k for k, v in MODE_NAMES.items()}

OK, CANCELLED, ERROR = 0, 1, 2

# Background (enum kz_background): keep it, leave it out around the picture, or leave its
# color out everywhere
BG_KEEP, BG_REMOVE, BG_REMOVE_ALL = 0, 1, 2
BG_NAMES = {BG_KEEP: "keep", BG_REMOVE: "remove", BG_REMOVE_ALL: "remove-all"}


class TraceError(Exception):
    pass


class Cancelled(Exception):
    pass


class _ColorEdit(ctypes.Structure):
    _fields_ = [("from_", ctypes.c_ubyte * 3), ("to", ctypes.c_ubyte * 3), ("leave_out", ctypes.c_int)]


class _Options(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_int),
        ("mode", ctypes.c_int),
        ("scans", ctypes.c_int),
        ("smooth", ctypes.c_int),
        ("stack", ctypes.c_int),
        ("remove_background", ctypes.c_int),
        ("threshold", ctypes.c_double),
        ("invert", ctypes.c_int),
        ("speckles", ctypes.c_int),
        ("smooth_corners", ctypes.c_double),
        ("optimize", ctypes.c_int),
        ("optimize_tolerance", ctypes.c_double),
        ("error_threshold", ctypes.c_double),
        ("filter_iterations", ctypes.c_int),
        ("preserve_width", ctypes.c_int),
        ("nedits", ctypes.c_int),
        ("edits", ctypes.POINTER(_ColorEdit)),
    ]


EDIT_MATCH = 24  # KZ_EDIT_MATCH: an edit applies to the palette color within this many levels


def edit_for(color, edits):
    """The edit (from, to) that applies to palette color <color>, as the engine picks it (the
    nearest original color within EDIT_MATCH levels in each channel, the first of equals), or None."""
    best, best_d = None, EDIT_MATCH + 1
    for e in edits:
        d = max(abs(a - b) for a, b in zip(color, e[0]))
        if d < best_d:
            best, best_d = e, d
    return best


@dataclass
class Options:
    """Tracing settings (the defaults are Inkscape's Trace Bitmap defaults)."""

    mode: int = COLORS
    scans: int = 8  # colors, grays or steps
    smooth: bool = True
    stack: bool = True
    remove_background: int = BG_KEEP  # BG_KEEP, BG_REMOVE or BG_REMOVE_ALL
    threshold: float = 0.45  # black and white cutoff / edge threshold
    invert: bool = False
    speckles: int = 2
    smooth_corners: float = 1.0
    optimize: bool = True
    optimize_tolerance: float = 0.2
    error_threshold: float = 2.0  # Autotrace
    filter_iterations: int = 4  # Autotrace
    preserve_width: bool = True  # Autotrace centerline
    # color edits: ((r, g, b) of a palette color, (r, g, b) to trace it as, or None: leave it out)
    edits: tuple = ()

    def _struct(self):
        s = _Options()
        s.size = ctypes.sizeof(_Options)
        for f in fields(self):
            if f.name == "edits":
                continue
            v = getattr(self, f.name)
            setattr(s, f.name, int(v) if isinstance(v, bool) else v)
        if self.edits:
            arr = (_ColorEdit * len(self.edits))()
            for e, (src, dst) in zip(arr, self.edits):
                e.from_[:] = [int(c) & 255 for c in src]
                e.to[:] = [int(c) & 255 for c in (dst or (0, 0, 0))]
                e.leave_out = 1 if dst is None else 0
            s.nedits = len(self.edits)
            s.edits = ctypes.cast(arr, ctypes.POINTER(_ColorEdit))
            s._edits_kept = arr     # (alive as long as the struct)
        return s


class _AutoInfo(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_int),
        ("colors", ctypes.c_int),
        ("transparent", ctypes.c_int),
        ("noisy", ctypes.c_int),
        ("photo", ctypes.c_int),
        ("wrong", ctypes.c_double),
        ("line_art", ctypes.c_int),
        ("enlarge", ctypes.c_int),
    ]


@dataclass
class AutoInfo:
    """What auto() found out about a picture."""

    colors: int
    transparent: bool
    noisy: bool
    photo: bool
    wrong: float  # fraction of the flat areas still off
    line_art: bool = False  # thin lines on a plain background
    enlarge: int = 0  # enlarge first: 4 for line art, 0 the usual


_PROGRESS = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_double, ctypes.c_void_p)


def _library_names():
    if sys.platform == "win32":
        return ["kzsvg.dll"]
    if sys.platform == "darwin":
        return ["libkzsvg.dylib"]
    return ["libkzsvg.so"]


def _library_dirs():
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = []
    if os.environ.get("KANZONASSVG_ENGINE_DIR"):
        dirs.append(os.environ["KANZONASSVG_ENGINE_DIR"])
    if getattr(sys, "frozen", False):
        dirs.append(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
        dirs.append(os.path.join(getattr(sys, "_MEIPASS", ""), "kanzonassvg", "lib"))
    dirs.append(os.path.join(here, "lib"))
    return dirs


_lib = None


def library():
    """Load the engine (once)."""
    global _lib
    if _lib is not None:
        return _lib
    tried = []
    for d in _library_dirs():
        for name in _library_names():
            path = os.path.join(d, name)
            tried.append(path)
            if os.path.exists(path):
                lib = ctypes.CDLL(path)
                break
        else:
            continue
        break
    else:
        raise TraceError(
            "The tracing engine isn't built. Run: python tools/build_engine.py\n(looked for "
            + ", ".join(tried) + ")"
        )
    lib.kz_default_options.argtypes = [ctypes.POINTER(_Options)]
    lib.kz_default_options.restype = None
    lib.kz_trace.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(_Options),
        _PROGRESS, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.kz_trace.restype = ctypes.c_int
    lib.kz_preview.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(_Options), ctypes.c_void_p,
    ]
    lib.kz_preview.restype = ctypes.c_int
    lib.kz_auto.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(_Options),
        ctypes.POINTER(_AutoInfo),
    ]
    lib.kz_auto.restype = ctypes.c_int
    lib.kz_palette.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(_Options),
                               ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    lib.kz_palette.restype = ctypes.c_int
    lib.kz_drawing_open.argtypes = [ctypes.c_char_p]
    lib.kz_drawing_open.restype = ctypes.c_void_p
    lib.kz_drawing_render.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
    lib.kz_drawing_render.restype = ctypes.c_int
    lib.kz_drawing_close.argtypes = [ctypes.c_void_p]
    lib.kz_drawing_close.restype = None
    lib.kz_free.argtypes = [ctypes.c_void_p]
    lib.kz_free.restype = None
    lib.kz_version.argtypes = []
    lib.kz_version.restype = ctypes.c_char_p
    _lib = lib
    return lib


def version():
    return library().kz_version().decode()


def _check_image(rgba, width, height, stride):
    if width <= 0 or height <= 0:
        raise TraceError("The image is empty.")
    if stride < width * 4 or len(rgba) < stride * (height - 1) + width * 4:
        raise TraceError("The image data is too short for its size.")


def trace(rgba, width, height, stride=None, options=None, progress=None):
    """Trace 8-bit RGBA pixels (bytes-like). Returns (svg text, number of shapes).

    progress(fraction) is called now and then; return True from it to stop (raises Cancelled).
    The engine runs without holding Python's lock, so this can run in a worker thread.
    """
    lib = library()
    stride = stride or width * 4
    _check_image(rgba, width, height, stride)
    opts = (options or Options())._struct()
    buf = (ctypes.c_char * len(rgba)).from_buffer_copy(rgba) if isinstance(rgba, bytes) else \
        (ctypes.c_char * len(rgba)).from_buffer(rgba)

    def cb(fraction, _data):
        try:
            return 1 if progress and progress(fraction) else 0
        except Exception:
            return 1

    cfunc = _PROGRESS(cb) if progress else _PROGRESS()
    svg = ctypes.c_void_p()
    err = ctypes.c_void_p()
    n = ctypes.c_int()
    status = lib.kz_trace(ctypes.addressof(buf), width, height, stride, ctypes.byref(opts), cfunc, None,
                          ctypes.byref(svg), ctypes.byref(n), ctypes.byref(err))
    try:
        if status == OK:
            return ctypes.string_at(svg.value).decode("utf-8"), n.value
        message = ctypes.string_at(err.value).decode("utf-8", "replace") if err.value else "tracing failed"
        if status == CANCELLED:
            raise Cancelled(message)
        raise TraceError(message)
    finally:
        if svg.value:
            lib.kz_free(svg)
        if err.value:
            lib.kz_free(err)


def palette(rgba, width, height, stride=None, options=None):
    """The colors a trace with <options> uses, darkest first as the layers are (before color
    edits), each with its pixel count: [((r, g, b), count)]. Empty in modes without colors.
    Fast after a trace of the same picture (the engine keeps them)."""
    lib = library()
    stride = stride or width * 4
    _check_image(rgba, width, height, stride)
    opts = (options or Options())._struct()
    buf = (ctypes.c_char * len(rgba)).from_buffer_copy(rgba) if isinstance(rgba, bytes) else \
        (ctypes.c_char * len(rgba)).from_buffer(rgba)
    rgb = (ctypes.c_ubyte * (256 * 3))()
    counts = (ctypes.c_longlong * 256)()
    n = ctypes.c_int(0)
    if lib.kz_palette(ctypes.addressof(buf), width, height, stride, ctypes.byref(opts), rgb, counts, 256,
                      ctypes.byref(n)) != OK:
        raise TraceError("Couldn't work out the colors.")
    return [((rgb[3 * k], rgb[3 * k + 1], rgb[3 * k + 2]), counts[k]) for k in range(n.value)]


def preview(rgba, width, height, stride=None, options=None):
    """The image as it will be traced: packed RGB bytes, width*height*3."""
    lib = library()
    stride = stride or width * 4
    _check_image(rgba, width, height, stride)
    opts = (options or Options())._struct()
    buf = (ctypes.c_char * len(rgba)).from_buffer_copy(rgba) if isinstance(rgba, bytes) else \
        (ctypes.c_char * len(rgba)).from_buffer(rgba)
    out = ctypes.create_string_buffer(width * height * 3)
    if lib.kz_preview(ctypes.addressof(buf), width, height, stride, ctypes.byref(opts), out) != OK:
        raise TraceError("The preview failed.")
    return out.raw


def auto(rgba, width, height, stride=None):
    """Recommended settings for a picture: (Options, AutoInfo)."""
    lib = library()
    stride = stride or width * 4
    _check_image(rgba, width, height, stride)
    buf = (ctypes.c_char * len(rgba)).from_buffer_copy(rgba) if isinstance(rgba, bytes) else \
        (ctypes.c_char * len(rgba)).from_buffer(rgba)
    opts = _Options()
    info = _AutoInfo()
    info.size = ctypes.sizeof(_AutoInfo)
    if lib.kz_auto(ctypes.addressof(buf), width, height, stride, ctypes.byref(opts), ctypes.byref(info)) != OK:
        raise TraceError("Couldn't work out settings for this picture.")
    o = Options()
    for f in fields(o):
        if f.name == "edits":
            continue
        v = getattr(opts, f.name)
        setattr(o, f.name, bool(v) if isinstance(getattr(o, f.name), bool) else v)
    return o, AutoInfo(info.colors, bool(info.transparent), bool(info.noisy), bool(info.photo), info.wrong,
                       bool(info.line_art), info.enlarge)


class Drawing:
    """An SVG this engine wrote, parsed once, to draw for the window (see kz_drawing_render)."""

    def __init__(self, svg):
        self._lib = library()
        self._handle = self._lib.kz_drawing_open(svg.encode("utf-8"))
        if not self._handle:
            raise TraceError("Couldn't read the SVG to show it.")

    def render(self, buffer_address, width, height, stride, left, top, target_width, target_height):
        """Draw into a premultiplied ARGB32 buffer (a QImage's bits). Python's lock is let go."""
        if self._lib.kz_drawing_render(self._handle, buffer_address, width, height, stride, left, top,
                                       target_width, target_height) != OK:
            raise TraceError("Couldn't draw the SVG.")

    def render_image(self, img, left, top, target_width, target_height):
        """Draw into a QImage (Format_ARGB32_Premultiplied)."""
        bits = img.bits()  # writable memoryview of the image's pixels
        buf = (ctypes.c_char * len(bits)).from_buffer(bits)
        self.render(ctypes.addressof(buf), img.width(), img.height(), img.bytesPerLine(), left, top,
                    target_width, target_height)

    def close(self):
        if self._handle:
            self._lib.kz_drawing_close(self._handle)
            self._handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
