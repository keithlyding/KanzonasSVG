// SPDX-License-Identifier: GPL-2.0-or-later
// libFuzzer target for the engine: any bytes become a small picture and settings, and go
// through kz_trace, kz_preview and kz_auto. It must never crash, hang, read or write out of
// bounds, or leak. Build and run: tests/fuzz_engine.sh [seconds]
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
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
    o.snap = data[11] >> 5;     // (snap shapes: any of the 3)
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
    // the trace drawn, filled and as outlines (the window's drawing)
    if (svg) {
        if (void *d = kz_drawing_open(svg)) {
            std::vector<unsigned char> buf((size_t)w * 4 * h);
            kz_drawing_render(d, buf.data(), w, h, w * 4, -data[0] / 7.0, -data[1] / 7.0, w * 1.7, h * 1.7);
            kz_drawing_render_outlines(d, buf.data(), w, h, w * 4, -data[0] / 7.0, -data[1] / 7.0, w * 1.7, h * 1.7, 1);
            kz_drawing_close(d);
        }
    }
    // and the input itself as an SVG to read (the reader only ever gets the engine's own; still)
    {
        std::string text((char const *)data, size);
        if (void *d = kz_drawing_open(text.c_str())) {
            std::vector<unsigned char> buf(16 * 4 * 16);
            kz_drawing_render(d, buf.data(), 16, 16, 64, 0, 0, 16, 16);
            kz_drawing_render_outlines(d, buf.data(), 16, 16, 64, 0, 0, 16, 16, 1);
            kz_drawing_close(d);
        }
    }
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
