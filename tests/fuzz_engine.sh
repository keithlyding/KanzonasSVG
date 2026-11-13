#!/bin/sh
# Fuzz the engine with libFuzzer (clang, with AddressSanitizer and UndefinedBehaviorSanitizer):
#   tests/fuzz_engine.sh [seconds] [jobs]
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/build/fuzz}
mkdir -p "$OUT/corpus"
SAN="-fsanitize=fuzzer,address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -g -O1"
C="$ROOT/core"
AT="$C/third_party/autotrace"
if [ ! -x "$OUT/fuzz_engine" ]; then
  for f in "$C"/third_party/potrace/curve.c "$C"/third_party/potrace/trace.c "$C"/third_party/potrace/decompose.c \
           "$C"/third_party/potrace/potracelib.c; do
    clang -fsanitize=fuzzer-no-link,address,undefined -fno-sanitize-recover=undefined -g -O1 -std=gnu99 \
        -DVERSION='"1.16"' -DHAVE_INTTYPES_H -c "$f" -o "$OUT/pt_$(basename "$f").o"
  done
  for f in "$AT"/src/autotrace/*.c; do
    clang -fsanitize=fuzzer-no-link,address,undefined -fno-sanitize-recover=undefined -g -O1 -std=gnu99 \
        -DHAVE_CONFIG_H -Wno-int-in-bool-context -I"$AT/shim" -I"$AT/include" -I"$AT/include/autotrace" \
        -I"$AT/src/autotrace" -c "$f" -o "$OUT/at_$(basename "$f").o"
  done
  clang++ $SAN -std=c++17 -I"$C/src" -I"$C/third_party/potrace" -I"$AT/shim" -I"$AT/include" \
      "$ROOT/tests/fuzz_engine.cpp" "$C"/src/engine.cpp "$C"/src/drawing.cpp "$C"/src/filterset.cpp "$C"/src/imagemap.cpp \
      "$C"/src/quantize.cpp "$OUT"/*.o -o "$OUT/fuzz_engine"
fi
cd "$OUT"
"$OUT/fuzz_engine" -max_total_time="${1:-60}" -jobs="${2:-1}" -workers="${2:-1}" -timeout=30 -rss_limit_mb=4096 \
    -print_final_stats=1 corpus
