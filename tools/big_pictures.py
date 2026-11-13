"""Big pictures: 24, 50 and 100 megapixels (the limit), and Enlarge 4 times on a 24-megapixel
one, each in its own process with a memory cap; time, memory and that nothing fails.

    python tools/big_pictures.py [--max-gb 9]
"""

import argparse
import os
import resource
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = r'''
import sys, os, time, resource
sys.path.insert(0, %r)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtCore import Qt
app = QGuiApplication([])
from kanzonassvg import engine, image, tracing
w, h, enlarge = WIDTH, HEIGHT, ENLARGE
src = QImage(os.path.join(%r, "tests", "reference", "starry-night.jpg")).scaled(
    w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
img = image.to_rgba(src)
t = time.time()
o, info = engine.auto(*image.pixels(img))
res = tracing.trace_image(img, o, enlarge)
print("%dx%d (%.0f MP), enlarge %d: %.1f s, %d colors, traced at %dx, %d paths, %.0f MB SVG, peak memory %.0f MB" % (
    w, h, w * h / 1e6, enlarge, time.time() - t, o.scans, res.factor, res.shapes, len(res.svg) / 1e6,
    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024))
'''.replace("%r", "{}").format(repr(ROOT), repr(ROOT))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--max-gb", type=float, default=9.0)
    args = a.parse_args()
    failed = 0
    for w, h, enlarge in ((6000, 4000, 1), (6000, 4000, 4), (8000, 6250, 1), (10000, 10000, 1)):
        def cap():
            lim = int(args.max_gb * 1024 ** 3)
            resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
        r = subprocess.run([sys.executable, "-c", CODE.replace('WIDTH', str(w)).replace('HEIGHT', str(h)).replace('ENLARGE', str(enlarge))], capture_output=True, text=True,
                           timeout=1800, preexec_fn=cap)
        out = [line for line in r.stdout.splitlines() if "propagate" not in line]
        if r.returncode != 0:
            failed += 1
            print("FAIL %dx%d enlarge %d: exit %d %s" % (w, h, enlarge, r.returncode, r.stderr[-500:]))
        else:
            print(out[-1])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
