#!/bin/bash
# Smoke test: the AppImage starts, opens a picture and stays up for a while (under Xvfb).
#   packaging/linux/smoke_test.sh ./KanzonasSVG-x86_64.AppImage [--appimage-extract-and-run]
set -u
APP="$1"; shift
python3 - <<'PY'
import struct, zlib
w, h = 64, 48
raw = b"".join(b"\0" + bytes([200, 30, 40] * w) for _ in range(h))
def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
open("smoke.png", "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                              + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
PY
xvfb-run -a -s "-screen 0 1280x800x24" "$APP" "$@" smoke.png > smoke.log 2>&1 &
PID=$!
sleep 15
if ! kill -0 "$PID" 2>/dev/null; then
  echo "::error::The AppImage exited early"; cat smoke.log; exit 1
fi
pkill -f "usr/lib/KanzonasSVG/KanzonasSVG" || true
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
echo "Smoke test passed"; cat smoke.log
