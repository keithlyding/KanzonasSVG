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


class TraceError(Exception):
    pass


class Cancelled(Exception):
    pass


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
    ]


@dataclass
class Options:
    """Tracing settings (the defaults are Inkscape's Trace Bitmap defaults)."""

    mode: int = COLORS
    scans: int = 8  # colors, grays or steps
    smooth: bool = True
    stack: bool = True
    remove_background: bool = False
    threshold: float = 0.45  # black and white cutoff / edge threshold
    invert: bool = False
    speckles: int = 2
    smooth_corners: float = 1.0
    optimize: bool = True
    optimize_tolerance: float = 0.2
    error_threshold: float = 2.0  # Autotrace
    filter_iterations: int = 4  # Autotrace
    preserve_width: bool = True  # Autotrace centerline

    def _struct(self):
        s = _Options()
        s.size = ctypes.sizeof(_Options)
        for f in fields(self):
            v = getattr(self, f.name)
            setattr(s, f.name, int(v) if isinstance(v, bool) else v)
        return s


class _AutoInfo(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_int),
        ("colors", ctypes.c_int),
        ("transparent", ctypes.c_int),
        ("noisy", ctypes.c_int),
        ("photo", ctypes.c_int),
        ("wrong", ctypes.c_double),
    ]


@dataclass
class AutoInfo:
    """What auto() found out about a picture."""

    colors: int
    transparent: bool
    noisy: bool
    photo: bool
    wrong: float  # fraction of the flat areas still off


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
        v = getattr(opts, f.name)
        setattr(o, f.name, bool(v) if isinstance(getattr(o, f.name), bool) else v)
    return o, AutoInfo(info.colors, bool(info.transparent), bool(info.noisy), bool(info.photo), info.wrong)
