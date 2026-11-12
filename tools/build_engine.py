"""Build the tracing engine (core/) and put it in kanzonassvg/lib/.

    python tools/build_engine.py [--debug]

Needs CMake and a C/C++ compiler (Visual Studio's on Windows, gcc or clang on Linux).
"""

import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    config = "Debug" if "--debug" in sys.argv else "Release"
    build = os.path.join(ROOT, "build", "engine")
    cmd = ["cmake", "-S", os.path.join(ROOT, "core"), "-B", build, "-DCMAKE_BUILD_TYPE=" + config]
    if sys.platform == "win32":
        cmd += ["-A", "x64"]
    subprocess.check_call(cmd)
    subprocess.check_call(["cmake", "--build", build, "--config", config, "--parallel"])
    names = {"win32": "kzsvg.dll", "darwin": "libkzsvg.dylib"}.get(sys.platform, "libkzsvg.so")
    found = [p for p in glob.glob(os.path.join(build, "**", names), recursive=True)]
    if not found:
        sys.exit("Built, but %s isn't in %s" % (names, build))
    dest = os.path.join(ROOT, "kanzonassvg", "lib")
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(found[0], os.path.join(dest, names))
    print("Engine:", os.path.join(dest, names))


if __name__ == "__main__":
    main()
