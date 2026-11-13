// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * A battery of random pictures and settings through the engine's C interface, to break it.
 *
 *   tests/engine_battery.sh [iterations] [seed]     (builds it with AddressSanitizer,
 *                                                    UndefinedBehaviorSanitizer, leak checks)
 *
 * Each step makes a picture (flat shapes with or without soft edges, noise, gradients, random
 * pixels, one-pixel patterns, transparency; from 1x1 to strips and a few hundred pixels) and
 * settings (any mode, extremes and nonsense values, an older or newer struct size), then
 * traces it, maybe cancelling partway, and checks:
 * - no crash, memory error, undefined behavior or leak (the sanitizers);
 * - the result: an SVG with the picture's size, as many <path> elements as it says, path data
 *   of M/L/C/Z and finite numbers within a margin of the picture, nothing else in it;
 * - fill colors: a picture of exact flat colors gives only colors it has;
 * - cancelling gives KZ_CANCELLED and no SVG; bad input gives KZ_ERROR, never a crash;
 * - the same input twice gives the same SVG (nothing read from uninitialized memory);
 * - preview writes exactly width*height*3 bytes; auto picks settings in range;
 * - no step takes longer than a limit.
 * Exits 1 and prints the seed and step of each failure (rerun with that seed to see it).
 */
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstddef>
#include <cstring>
#include <random>
#include <set>
#include <string>
#include <vector>

#include "kzsvg.h"

namespace {

struct Pic
{
    int w, h, stride;
    std::vector<unsigned char> px; // RGBA, stride bytes per row
    bool exact = false;            // only flat colors, no soft edges, opaque
    std::set<uint32_t> colors;     // the colors of an exact picture
    std::string kind;
};

using Rng = std::mt19937_64;

int rnd(Rng &r, int lo, int hi) // lo..hi inclusive
{
    return std::uniform_int_distribution<int>(lo, hi)(r);
}

double rndf(Rng &r, double lo, double hi)
{
    return std::uniform_real_distribution<double>(lo, hi)(r);
}

uint32_t pack(int r, int g, int b) { return (uint32_t)r << 16 | (uint32_t)g << 8 | (uint32_t)b; }

Pic make_picture(Rng &r)
{
    Pic p;
    // sizes: mostly modest, sometimes degenerate
    switch (rnd(r, 0, 9)) {
        case 0: p.w = 1; p.h = 1; break;
        case 1: p.w = rnd(r, 1, 3); p.h = rnd(r, 1, 600); break;
        case 2: p.w = rnd(r, 1, 600); p.h = rnd(r, 1, 3); break;
        case 3: p.w = rnd(r, 2, 8); p.h = rnd(r, 2, 8); break;
        default: p.w = rnd(r, 8, 360); p.h = rnd(r, 8, 260); break;
    }
    p.stride = p.w * 4 + (rnd(r, 0, 3) == 0 ? rnd(r, 1, 64) : 0);
    p.px.assign((size_t)p.stride * p.h, 0xA5); // padding with junk: must never be read as pixels
    int ncol = rnd(r, 1, 12);
    std::vector<uint32_t> pal;
    for (int i = 0; i < ncol; i++) {
        pal.push_back(rnd(r, 0, 3) == 0 ? pack(rnd(r, 0, 1) * 255, rnd(r, 0, 1) * 255, rnd(r, 0, 1) * 255)
                                        : pack(rnd(r, 0, 255), rnd(r, 0, 255), rnd(r, 0, 255)));
    }
    auto put = [&](int x, int y, uint32_t c, int a = 255) {
        auto q = &p.px[(size_t)y * p.stride + x * 4];
        q[0] = c >> 16;
        q[1] = c >> 8 & 255;
        q[2] = c & 255;
        q[3] = a;
    };
    int kind = rnd(r, 0, 9);
    if (kind <= 3) {
        // flat shapes: rectangles, ellipses and rings, maybe anti-aliased (supersampled)
        p.kind = "shapes";
        int ss = rnd(r, 0, 1) ? 1 : 4;
        p.exact = ss == 1;
        struct Shape { int type; double cx, cy, rx, ry, t; uint32_t c; };
        std::vector<Shape> shapes;
        int n = rnd(r, 0, 12);
        for (int i = 0; i < n; i++) {
            shapes.push_back({rnd(r, 0, 2), rndf(r, 0, p.w), rndf(r, 0, p.h), rndf(r, 0.5, p.w / 2.0 + 1),
                              rndf(r, 0.5, p.h / 2.0 + 1), rndf(r, 0.5, 8), pal[rnd(r, 0, ncol - 1)]});
        }
        uint32_t bg = pal[0];
        for (int y = 0; y < p.h; y++) {
            for (int x = 0; x < p.w; x++) {
                double acc[3] = {0, 0, 0};
                uint32_t last = bg;
                for (int sy = 0; sy < ss; sy++) {
                    for (int sx = 0; sx < ss; sx++) {
                        double fx = x + (sx + 0.5) / ss, fy = y + (sy + 0.5) / ss;
                        uint32_t c = bg;
                        for (auto const &s : shapes) {
                            double dx = (fx - s.cx) / s.rx, dy = (fy - s.cy) / s.ry;
                            double d = dx * dx + dy * dy;
                            bool in = s.type == 0 ? std::fabs(fx - s.cx) < s.rx && std::fabs(fy - s.cy) < s.ry
                                    : s.type == 1 ? d < 1
                                                  : d < 1 && std::sqrt(d) > 1 - s.t / std::max(s.rx, s.ry);
                            if (in) {
                                c = s.c;
                            }
                        }
                        acc[0] += c >> 16;
                        acc[1] += c >> 8 & 255;
                        acc[2] += c & 255;
                        last = c;
                    }
                }
                int n2 = ss * ss;
                uint32_t c = ss == 1 ? last
                                     : pack((int)(acc[0] / n2 + 0.5), (int)(acc[1] / n2 + 0.5), (int)(acc[2] / n2 + 0.5));
                put(x, y, c);
                if (p.exact) {
                    p.colors.insert(c);
                }
            }
        }
    } else if (kind == 4) {
        p.kind = "noise";
        for (int y = 0; y < p.h; y++)
            for (int x = 0; x < p.w; x++)
                put(x, y, pack(rnd(r, 0, 255), rnd(r, 0, 255), rnd(r, 0, 255)), rnd(r, 0, 3) ? 255 : rnd(r, 0, 255));
    } else if (kind == 5) {
        p.kind = "gradient";
        for (int y = 0; y < p.h; y++)
            for (int x = 0; x < p.w; x++)
                put(x, y, pack(x * 255 / std::max(1, p.w - 1), y * 255 / std::max(1, p.h - 1), (x + y) & 255));
    } else if (kind == 6) {
        p.kind = "checker";
        int cell = rnd(r, 1, 3);
        p.exact = true;
        for (int y = 0; y < p.h; y++)
            for (int x = 0; x < p.w; x++) {
                uint32_t c = pal[((x / cell) + (y / cell)) % std::min(2, ncol)];
                put(x, y, c);
                p.colors.insert(c);
            }
    } else if (kind == 7) {
        p.kind = "transparent";
        int mode = rnd(r, 0, 2); // all clear, half clear, partial alpha
        for (int y = 0; y < p.h; y++)
            for (int x = 0; x < p.w; x++)
                put(x, y, pal[(x * 7 / std::max(1, p.w)) % ncol],
                    mode == 0 ? 0 : mode == 1 ? (x < p.w / 2 ? 0 : 255) : rnd(r, 0, 255));
    } else if (kind == 8) {
        p.kind = "solid";
        p.exact = true;
        for (int y = 0; y < p.h; y++)
            for (int x = 0; x < p.w; x++)
                put(x, y, pal[0]);
        p.colors.insert(pal[0]);
    } else {
        p.kind = "noisy-shapes";
        for (int y = 0; y < p.h; y++)
            for (int x = 0; x < p.w; x++) {
                uint32_t c = pal[((x * 3 / std::max(1, p.w)) + (y * 2 / std::max(1, p.h)) * 3) % ncol];
                int d = rnd(r, -20, 20);
                auto cl = [&](int v) { return std::max(0, std::min(255, v + d)); };
                put(x, y, pack(cl(c >> 16), cl(c >> 8 & 255), cl(c & 255)));
            }
    }
    return p;
}

kz_options make_options(Rng &r)
{
    kz_options o;
    kz_default_options(&o);
    o.mode = rnd(r, 0, 20) == 0 ? rnd(r, -3, 50) : rnd(r, 0, 6);
    switch (rnd(r, 0, 5)) {
        case 0: o.scans = rnd(r, -10, 1); break;
        case 1: o.scans = rnd(r, 200, 100000); break;
        default: o.scans = rnd(r, 2, 32); break;
    }
    o.smooth = rnd(r, 0, 1);
    o.stack = rnd(r, 0, 1);
    o.remove_background = rnd(r, 0, 12) == 0 ? rnd(r, -5, 9) : rnd(r, 0, 2);
    o.threshold = rnd(r, 0, 9) == 0 ? rndf(r, -5, 5) : rndf(r, 0, 1);
    o.invert = rnd(r, 0, 1);
    o.speckles = rnd(r, 0, 9) == 0 ? rnd(r, -100, 1000000) : rnd(r, 0, 20);
    o.smooth_corners = rnd(r, 0, 9) == 0 ? rndf(r, -10, 10) : rndf(r, 0, 1.34);
    o.optimize = rnd(r, 0, 1);
    o.optimize_tolerance = rnd(r, 0, 9) == 0 ? rndf(r, -10, 100) : rndf(r, 0, 1);
    o.error_threshold = rnd(r, 0, 9) == 0 ? rndf(r, -10, 1e9) : rndf(r, 0.5, 4);
    o.filter_iterations = rnd(r, 0, 9) == 0 ? rnd(r, -10, 1000) : rnd(r, 0, 8);
    o.preserve_width = rnd(r, 0, 1);
    if (rnd(r, 0, 9) == 0) {
        o.threshold = NAN;
        o.smooth_corners = INFINITY;
    }
    return o;
}

struct Failure
{
    std::string what;
};

// The checks on a traced SVG.
void check_svg(std::string const &svg, Pic const &p, int nshapes, kz_options const &o, std::vector<std::string> &errs)
{
    auto fail = [&](std::string const &m) { errs.push_back(m); };
    std::string head = "viewBox=\"0 0 " + std::to_string(p.w) + " " + std::to_string(p.h) + "\"";
    if (svg.rfind("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n", 0) != 0) fail("no XML declaration");
    if (svg.find(head) == std::string::npos) fail("no " + head);
    if (svg.size() < 7 || svg.compare(svg.size() - 7, 7, "</svg>\n") != 0) fail("doesn't end with </svg>");
    int paths = 0;
    size_t pos = 0;
    std::set<uint32_t> fills;
    while ((pos = svg.find("<path ", pos)) != std::string::npos) {
        paths++;
        size_t end = svg.find("/>", pos);
        if (end == std::string::npos) { fail("unterminated <path"); break; }
        std::string el = svg.substr(pos, end - pos);
        size_t f = el.find("fill:#");
        if (f != std::string::npos) {
            fills.insert((uint32_t)std::strtoul(el.substr(f + 6, 6).c_str(), nullptr, 16));
        }
        size_t d = el.find(" d=\"");
        if (d == std::string::npos) { fail("<path without d"); pos = end; continue; }
        std::string data = el.substr(d + 4, el.find('"', d + 4) - d - 4);
        if (data.empty()) fail("empty path data");
        // M/L/C/Z, numbers, commas and spaces only; numbers finite and near the picture
        const char *c = data.c_str();
        double margin = 2.0 * std::max(p.w, p.h) + 10;
        while (*c) {
            if (strchr("MLCZ ,", *c)) { c++; continue; }
            char *e;
            double v = std::strtod(c, &e);
            if (e == c) { fail(std::string("bad character in path data: '") + *c + "'"); break; }
            if (!std::isfinite(v) || v < -margin || v > margin) {
                fail("coordinate out of range: " + std::to_string(v));
                break;
            }
            c = e;
        }
        if (data[0] != 'M') fail("path data doesn't start with M");
        pos = end;
    }
    if (paths != nshapes) fail("nshapes " + std::to_string(nshapes) + " but " + std::to_string(paths) + " <path>");
    // exact colors (Potrace color modes: the palette colors come from the picture; Grays makes grays of them)
    // (Smooth off: smoothing a clean picture softens hard edges, and a thin rim of the mix of two
    // colors can stay where a shape is too small to tell it from a color of its own.)
    // (and no more colors in the picture than asked for: more are merged, into a color between them)
    if (p.exact && o.mode == KZ_COLORS && !o.smooth && o.scans >= 2 && o.scans <= 256 &&
        (int)p.colors.size() <= o.scans) {
        for (auto f : fills) {
            if (!p.colors.count(f)) {
                char buf[64];
                std::snprintf(buf, sizeof buf, "fill #%06x isn't a color of the picture", f);
                fail(buf);
                break;
            }
        }
    }
}

struct Cancel
{
    int after; // calls before stopping (-1: never)
    int calls = 0;
    double last = -1;
    bool backwards = false;
};

int progress(double f, void *data)
{
    auto c = static_cast<Cancel *>(data);
    if (f < c->last - 1e-9 || f < 0 || f > 1 + 1e-9) c->backwards = true;
    c->last = f;
    c->calls++;
    return c->after >= 0 && c->calls > c->after;
}

} // namespace

int main(int argc, char **argv)
{
    long iterations = argc > 1 ? std::atol(argv[1]) : 2000;
    uint64_t seed = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 1;
    long first = std::getenv("KZ_STEP") ? std::atol(std::getenv("KZ_STEP")) : 0; // rerun one step
    double limit = argc > 3 ? std::atof(argv[3]) : 20.0; // seconds per step (sanitizers are slow)
    int failures = 0;
    double slowest = 0;
    std::printf("engine battery: %ld steps, seed %llu\n", iterations, (unsigned long long)seed);

    // bad input never crashes
    {
        kz_options o;
        kz_default_options(&o);
        char *svg = (char *)1, *err = nullptr;
        unsigned char px[16] = {0};
        struct { const unsigned char *p; int w, h, s; } bad[] = {
            {nullptr, 1, 1, 4}, {px, 0, 1, 4}, {px, 1, 0, 4}, {px, -1, 1, 4}, {px, 2, 2, 4}, {px, 100000, 100000, 400000},
        };
        for (auto const &b : bad) {
            int st = kz_trace(b.p, b.w, b.h, b.s, &o, nullptr, nullptr, &svg, nullptr, &err);
            if (st != KZ_ERROR || svg) { std::printf("FAIL bad input %dx%d: status %d\n", b.w, b.h, st); failures++; }
            kz_free(err);
            err = nullptr;
            if (kz_preview(b.p, b.w, b.h, b.s, &o, px) != KZ_ERROR) { std::printf("FAIL bad preview\n"); failures++; }
            kz_options a;
            if (kz_auto(b.p, b.w, b.h, b.s, &a, nullptr) != KZ_ERROR) { std::printf("FAIL bad auto\n"); failures++; }
        }
        if (kz_trace(px, 1, 1, 4, &o, nullptr, nullptr, nullptr, nullptr, nullptr) != KZ_ERROR) {
            std::printf("FAIL no place for the result\n");
            failures++;
        }
    }

    for (long step = first; step < (std::getenv("KZ_STEP") ? first + 1 : iterations); step++) {
        Rng r(seed * 1000003ULL + step);
        Pic p = make_picture(r);
        kz_options o = make_options(r);
        if (rnd(r, 0, 9) == 0) o.size = rnd(r, 0, (int)sizeof(o)); // an older caller's smaller struct
        Cancel cancel{rnd(r, 0, 5) == 0 ? rnd(r, 0, 30) : -1};
        std::vector<std::string> errs;

        auto t0 = std::chrono::steady_clock::now();
        char *svg = nullptr, *err = nullptr;
        int n = -1;
        int st = kz_trace(p.px.data(), p.w, p.h, p.stride, &o, rnd(r, 0, 3) ? progress : nullptr, &cancel, &svg, &n,
                          &err);
        if (st == KZ_OK) {
            if (!svg) errs.push_back("OK without an SVG");
            else {
                kz_options eff = o;
                if (o.size != (int)sizeof(o)) {
                    kz_options d;
                    kz_default_options(&d);
                    eff = d;
                    std::memcpy(&eff, &o, std::max(0, std::min(o.size, (int)sizeof(o))));
                }
                eff.scans = std::max(2, std::min(256, eff.scans));
                check_svg(svg, p, n, eff, errs);
                // the same again (only without cancelling): the same SVG
                if (cancel.after < 0 && rnd(r, 0, 3) == 0) {
                    char *svg2 = nullptr, *err2 = nullptr;
                    int n2 = 0;
                    if (kz_trace(p.px.data(), p.w, p.h, p.stride, &o, nullptr, nullptr, &svg2, &n2, &err2) != KZ_OK ||
                        std::strcmp(svg, svg2) != 0)
                        errs.push_back("a second trace gave another SVG");
                    kz_free(svg2);
                    kz_free(err2);
                }
            }
            if (err) errs.push_back("OK with an error message");
        } else if (st == KZ_CANCELLED) {
            if (cancel.after < 0) errs.push_back("cancelled without being asked");
            if (svg) errs.push_back("cancelled with an SVG");
        } else if (st == KZ_ERROR) {
            bool nonsense_mode = o.size >= (int)(offsetof(kz_options, mode) + sizeof(int)) && (o.mode < 0 || o.mode > 6);
            if (!nonsense_mode || !err) errs.push_back(std::string("error: ") + (err ? err : "(no message)"));
        } else {
            errs.push_back("unknown status " + std::to_string(st));
        }
        if (cancel.backwards) errs.push_back("progress went backwards or out of 0..1");
        kz_free(svg);
        kz_free(err);

        // preview: exactly w*h*3 bytes (an exactly sized buffer: AddressSanitizer catches more)
        if (rnd(r, 0, 2) == 0) {
            std::vector<unsigned char> out((size_t)p.w * p.h * 3);
            int ps = kz_preview(p.px.data(), p.w, p.h, p.stride, &o, out.data());
            if (ps != KZ_OK && o.mode >= 0 && o.mode <= 6) errs.push_back("preview failed");
        }
        // auto: settings in range
        if (rnd(r, 0, 2) == 0) {
            kz_options a;
            kz_auto_info info;
            info.size = rnd(r, 0, 1) ? (int)sizeof(info) : rnd(r, 0, (int)sizeof(info));
            if (kz_auto(p.px.data(), p.w, p.h, p.stride, &a, &info) != KZ_OK) errs.push_back("auto failed");
            else if (a.mode < 0 || a.mode > 6 || a.scans < 2 || a.scans > 16 || a.remove_background < 0 ||
                     a.remove_background > 2 || !(a.threshold >= 0 && a.threshold <= 1))
                errs.push_back("auto picked settings out of range");
        }

        double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
        slowest = std::max(slowest, secs);
        if (secs > limit) errs.push_back("took " + std::to_string(secs) + " s");

        if (!errs.empty() && std::getenv("KZ_DUMP")) {
            // the picture as a PAM file (RGBA), to look at the failure
            FILE *f = std::fopen(std::getenv("KZ_DUMP"), "wb");
            std::fprintf(f, "P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n", p.w, p.h);
            for (int y = 0; y < p.h; y++) std::fwrite(&p.px[(size_t)y * p.stride], 4, p.w, f);
            std::fclose(f);
        }
        for (auto const &e : errs) {
            std::printf("FAIL seed %llu step %ld (%s %dx%d stride %d, mode %d, scans %d, bg %d): %s\n",
                        (unsigned long long)seed, step, p.kind.c_str(), p.w, p.h, p.stride, o.mode, o.scans,
                        o.remove_background, e.c_str());
        }
        failures += !errs.empty();
        if ((step + 1) % 500 == 0) {
            std::printf("  %ld steps, %d failed, slowest %.2f s\n", step + 1, failures, slowest);
            std::fflush(stdout);
        }
    }
    std::printf("%s: %d failed steps, slowest %.2f s\n", failures ? "FAILED" : "PASSED", failures, slowest);
    return failures ? 1 : 0;
}
