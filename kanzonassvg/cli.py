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
        "  kanzonassvg logo.png                  -> logo.svg, settings picked for it\n"
        "  kanzonassvg --colors 4 *.png -o out   -> out/<name>.svg for each\n"
        "  kanzonassvg --mode bw scan.jpg -o scan.svg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("inputs", nargs="+", metavar="PICTURE", help="pictures to trace (wildcards work)")
    p.add_argument("-o", "--output", metavar="PATH",
                   help="the SVG file (one picture), or a folder for them (default: next to each picture)")
    p.add_argument("-f", "--force", action="store_true", help="replace SVG files that are already there")
    p.add_argument("--no-auto", action="store_true",
                   help="don't pick settings for each picture: use the defaults (8 colors, smoothed) and "
                   "the options given. Without it, each picture gets the settings that suit it (mode, "
                   "colors, smoothing, background, threshold), and the options given replace them")
    p.add_argument("--mode", default=None, choices=sorted(engine.MODES_BY_NAME), help=MODE_HELP)
    p.add_argument("--colors", "--scans", type=int, default=None, metavar="N",
                   help="colors, grays or steps (2-256)")
    p.add_argument("--smooth", action=argparse.BooleanOptionalAction, default=None,
                   help="smooth noise before reducing colors (--no-smooth: don't)")
    p.add_argument("--tile", action="store_true", help="tile the color layers instead of stacking them")
    p.add_argument("--remove-background", action=argparse.BooleanOptionalAction, default=None,
                   help="leave out the background layer (--no-remove-background: keep it)")
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


def options_from(args, picked=None):
    """The options for one picture: <picked> (Auto's, or the defaults) with the ones given."""
    base = picked or engine.Options()
    mode = engine.MODES_BY_NAME[args.mode] if args.mode else base.mode
    threshold = args.threshold
    if threshold is None:
        if mode == engine.EDGES:
            threshold = 0.65
        elif mode == base.mode:
            threshold = base.threshold
        else:
            threshold = 0.45
    return engine.Options(
        mode=mode,
        scans=args.colors if args.colors is not None else base.scans,
        smooth=args.smooth if args.smooth is not None else base.smooth,
        stack=not args.tile,
        remove_background=args.remove_background if args.remove_background is not None
        else base.remove_background and mode in (engine.COLORS, engine.GRAYS, engine.BRIGHTNESS_STEPS),
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
            note = ""
            if args.no_auto:
                options = options_from(args)
            else:
                picked, _info = engine.auto(*image.pixels(img))
                options = options_from(args, picked)
                note = ", %s" % ("black and white" if options.mode == engine.BRIGHTNESS
                                 else "%d %s" % (options.scans, engine.MODE_NAMES[options.mode]))
            res = tracing.trace_image(img, options, enlarge)
            tmp = dst + ".part"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(res.svg)
            os.replace(tmp, dst)
            if not args.quiet:
                print("%s -> %s (%d shapes, %.0f KB, %.2f s%s%s)" % (
                    src, dst, res.shapes, len(res.svg.encode()) / 1024, res.seconds, note,
                    ", traced at %dx" % res.factor if res.factor != 1 else ""))
        except (image.ImageError, engine.TraceError, OSError) as e:
            failed += 1
            print("%s: %s" % (src, e), file=sys.stderr)
    return 1 if failed else 0
