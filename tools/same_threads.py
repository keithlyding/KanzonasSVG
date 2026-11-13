"""The engine gives the same SVG on any number of threads (KZ_THREADS=1, 2, 4, 8): every
reference picture, every mode, background kept or removed. Exit 1 if any differs."""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = r'''
import sys, os, hashlib, json
sys.path.insert(0, %r)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
from kanzonassvg import engine, image
ref = os.path.join(%r, "tests", "reference")
out = {}
for name in sorted(os.listdir(ref)):
    if not name.endswith((".png", ".jpg")):
        continue
    img = image.load(os.path.join(ref, name))
    for mode in engine.MODE_NAMES:
        for bg in (0, 1, 2):
            svg, n = engine.trace(*image.pixels(img), options=engine.Options(mode=mode, scans=9, remove_background=bg))
            out["%%s %%s %%d" %% (name, engine.MODE_NAMES[mode], bg)] = hashlib.sha256(svg.encode()).hexdigest()
print(json.dumps(out))
''' % (ROOT, ROOT)


def main():
    res = {}
    for t in ("1", "2", "4", "8"):
        r = subprocess.run([sys.executable, "-c", CODE], env=dict(os.environ, KZ_THREADS=t), capture_output=True,
                           text=True, timeout=3600)
        res[t] = json.loads(r.stdout.strip().splitlines()[-1])
    diff = [k for k in res["1"] if len({res[t][k] for t in res}) > 1]
    print("%d cases (pictures x modes x backgrounds) on 1, 2, 4 and 8 threads: %s"
          % (len(res["1"]), "all the same" if not diff else "DIFFERENT: %s" % diff))
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
