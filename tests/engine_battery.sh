#!/bin/sh
# Build the engine battery with AddressSanitizer, UndefinedBehaviorSanitizer and leak checks,
# and run it:  tests/engine_battery.sh [iterations] [seed] [seconds per step]
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/build/battery}
mkdir -p "$OUT"
CXX=${CXX:-clang++}
CC=${CC:-clang}
SAN="-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -g -O1"
C="$ROOT/core"
AT="$C/third_party/autotrace"
for f in "$C"/third_party/potrace/curve.c "$C"/third_party/potrace/trace.c "$C"/third_party/potrace/decompose.c \
         "$C"/third_party/potrace/potracelib.c; do
  $CC $SAN -std=gnu99 -DVERSION='"1.16"' -DHAVE_INTTYPES_H -c "$f" -o "$OUT/pt_$(basename "$f").o"
done
for f in "$AT"/src/autotrace/*.c; do
  $CC $SAN -std=gnu99 -DHAVE_CONFIG_H -Wno-int-in-bool-context -I"$AT/shim" -I"$AT/include" \
      -I"$AT/include/autotrace" -I"$AT/src/autotrace" -c "$f" -o "$OUT/at_$(basename "$f").o"
done
$CXX $SAN -std=c++17 -I"$C/src" -I"$C/third_party/potrace" -I"$AT/shim" -I"$AT/include" \
    "$ROOT/tests/engine_battery.cpp" "$C"/src/engine.cpp "$C"/src/filterset.cpp "$C"/src/imagemap.cpp \
    "$C"/src/quantize.cpp "$OUT"/*.o -o "$OUT/engine_battery"
ASAN_OPTIONS=${ASAN_OPTIONS:-detect_leaks=1:abort_on_error=1} \
UBSAN_OPTIONS=${UBSAN_OPTIONS:-print_stacktrace=1:halt_on_error=1} \
  "$OUT/engine_battery" "$@"
