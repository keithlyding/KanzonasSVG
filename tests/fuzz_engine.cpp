// SPDX-License-Identifier: GPL-2.0-or-later
// libFuzzer target for the engine: any bytes become a small picture and settings, and go
// through kz_trace, kz_preview and kz_auto. It must never crash, hang, read or write out of
// bounds, or leak. Build and run: tests/fuzz_engine.sh [seconds]
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

#include "kzsvg.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    if (size < 24) {
        return 0;
    }
    int w = 1 + data[0] % 96, h = 1 + data[1] % 96;
    int pad = data[2] % 8;
    kz_options o;
    kz_default_options(&o);
    o.mode = data[3] % 8; // 7: an unknown mode
    o.scans = (int)data[4] - 8;
    o.smooth = data[5] & 1;
    o.stack = data[5] >> 1 & 1;
    o.remove_background = data[5] >> 2 & 3;
    o.invert = data[5] >> 4 & 1;
    o.optimize = data[5] >> 5 & 1;
    o.preserve_width = data[5] >> 6 & 1;
    o.threshold = data[6] / 200.0;
    o.speckles = data[7] % 64;
    o.smooth_corners = data[8] / 150.0;
    o.optimize_tolerance = data[9] / 40.0;
    o.error_threshold = data[10] / 20.0;
    o.filter_iterations = data[11] % 24;
    data += 12;
    size -= 12;
    int stride = w * 4 + pad;
    std::vector<unsigned char> px((size_t)stride * h);
    // the pixels: the rest of the input, repeated (small inputs still fill a picture)
    for (size_t i = 0; i < px.size(); i++) {
        px[i] = data[i % size];
    }
    char *svg = nullptr, *err = nullptr;
    int n = 0;
    kz_trace(px.data(), w, h, stride, &o, nullptr, nullptr, &svg, &n, &err);
    kz_free(svg);
    kz_free(err);
    std::vector<unsigned char> out((size_t)w * h * 3);
    kz_preview(px.data(), w, h, stride, &o, out.data());
    kz_options a;
    kz_auto_info info;
    info.size = sizeof(info);
    kz_auto(px.data(), w, h, stride, &a, &info);
    return 0;
}
