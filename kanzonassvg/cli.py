"""The command line: trace one or many pictures into SVG files."""

import argparse
import glob
import os
import sys

from kanzonassvg import APP_NAME, __version__, engine, image, tracing

MODE_HELP = (
    "colors (default), grays, steps (brightness steps), bw (black and white), edges, "
    "autotrace (colors with Autotrace), centerline (lines along the middle of strokes)"
)


def parser():
    p = argparse.ArgumentParser(
        prog="kanzonassvg-cli" if sys.platform == "win32" else "kanzonassvg",
        description="Turn pictures (PNG, JPEG, BMP, GIF, WebP, TIFF...) into SVG files.",
        epilog="Examples:\n"
        "  kanzonassvg logo.png                  -> logo.svg, 8 colors\n"
        "  kanzonassvg --colors 4 *.png -o out   -> out/<name>.svg for each\n"
        "  kanzonassvg --mode bw scan.jpg -o scan.svg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("inputs", nargs="+", metavar="PICTURE", help="pictures to trace (wildcards work)")
    p.add_argument("-o", "--output", metavar="PATH",
                   help="the SVG file (one picture), or a folder for them (default: next to each picture)")
    p.add_argument("-f", "--force", action="store_true", help="replace SVG files that are already there")
    p.add_argument("--mode", default="colors", choices=sorted(engine.MODES_BY_NAME), help=MODE_HELP)
    p.add_argument("--colors", "--scans", type=int, default=8, metavar="N",
                   help="colors, grays or steps (2-256; default 8)")
    p.add_argument("--no-smooth", action="store_true", help="don't smooth before reducing colors")
    p.add_argument("--tile", action="store_true", help="tile the color layers instead of stacking them")
    p.add_argument("--remove-background", action="store_true", help="leave out the background layer")
    p.add_argument("--threshold", type=float, default=None, metavar="0-1",
                   help="black and white: brightness cutoff (default 0.45); edges: edge threshold (default 0.65)")
    p.add_argument("--invert", action="store_true", help="black and white, edges: trace the light parts")
    p.add_argument("--speckles", type=int, default=2, metavar="PX",
                   help="drop spots of up to this many pixels (default 2)")
    p.add_argument("--smooth-corners", type=float, default=1.0, metavar="0-1.34",
                   help="0 keeps every corner sharp, 1.34 rounds them (default 1)")
    p.add_argument("--no-optimize", action="store_true", help="don't join curve segments (bigger files)")
    p.add_argument("--tolerance", type=float, default=0.2, metavar="0-5",
                   help="how far joining segments may move the curve (default 0.2)")
    p.add_argument("--enlarge", default="auto", choices=["auto", "1", "2", "4"],
                   help="trace at this many times the size (auto: 2 for pictures under %d pixels)"
                   % tracing.AUTO_BELOW)
    p.add_argument("--error-threshold", type=float, default=2.0, metavar="PX",
                   help="Autotrace: how far a curve may be from the outline (default 2)")
    p.add_argument("--filter-iterations", type=int, default=4, metavar="N",
                   help="Autotrace: smoothing passes on outlines (default 4)")
    p.add_argument("--no-preserve-width", action="store_true", help="centerline: don't keep line widths")
    p.add_argument("-q", "--quiet", action="store_true", help="print only errors")
    p.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    return p


def options_from(args):
    mode = engine.MODES_BY_NAME[args.mode]
    threshold = args.threshold
    if threshold is None:
        threshold = 0.65 if mode == engine.EDGES else 0.45
    return engine.Options(
        mode=mode,
        scans=args.colors,
        smooth=not args.no_smooth,
        stack=not args.tile,
        remove_background=args.remove_background,
        threshold=threshold,
        invert=args.invert,
        speckles=args.speckles,
        smooth_corners=args.smooth_corners,
        optimize=not args.no_optimize,
        optimize_tolerance=args.tolerance,
        error_threshold=args.error_threshold,
        filter_iterations=args.filter_iterations,
        preserve_width=not args.no_preserve_width,
    )


def expand(inputs):
    files = []
    for item in inputs:
        matches = [m for m in sorted(glob.glob(item)) if os.path.isfile(m)] if any(c in item for c in "*?[") else [item]
        if not matches:
            print("No pictures match %s" % item, file=sys.stderr)
        files.extend(matches)
    return files


def output_path(src, output, many):
    base = os.path.splitext(os.path.basename(src))[0] + ".svg"
    if not output:
        return os.path.join(os.path.dirname(os.path.abspath(src)), base)
    if many or os.path.isdir(output) or output.endswith(("/", "\\")):
        return os.path.join(output, base)
    return output


_APP = None


def qt_app():
    """Qt's picture readers want an application (no window is shown)."""
    global _APP
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None:
        if not os.environ.get("QT_QPA_PLATFORM"):
            # no screen needed: never fail for want of one (a server, a script over SSH)
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
        _APP = QGuiApplication(["kanzonassvg"])
    return QGuiApplication.instance()


def run(argv):
    args = parser().parse_args(argv)
    qt_app()
    options = options_from(args)
    enlarge = tracing.AUTO if args.enlarge == "auto" else int(args.enlarge)
    files = expand(args.inputs)
    if not files:
        return 2
    many = len(files) > 1
    if many and args.output and not os.path.isdir(args.output):
        if os.path.exists(args.output):
            print("%s isn't a folder: with several pictures, -o names a folder." % args.output, file=sys.stderr)
            return 2
        os.makedirs(args.output)
    failed = 0
    for src in files:
        dst = output_path(src, args.output, many)
        try:
            if os.path.exists(dst) and not args.force:
                raise image.ImageError("%s is already there (use -f to replace it)" % dst)
            img = image.load(src)
            res = tracing.trace_image(img, options, enlarge)
            tmp = dst + ".part"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(res.svg)
            os.replace(tmp, dst)
            if not args.quiet:
                print("%s -> %s (%d shapes, %.0f KB, %.2f s%s)" % (
                    src, dst, res.shapes, len(res.svg.encode()) / 1024, res.seconds,
                    ", traced at %dx" % res.factor if res.factor != 1 else ""))
        except (image.ImageError, engine.TraceError, OSError) as e:
            failed += 1
            print("%s: %s" % (src, e), file=sys.stderr)
    return 1 if failed else 0
