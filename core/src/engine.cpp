// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * KanzonasSVG engine: Inkscape's Trace Bitmap (Potrace and Autotrace) as a library
 * that turns a bitmap straight into an SVG document.
 *
 * Adapted from Inkscape's src/trace/potrace/inkscape-potrace.cpp
 * (Bob Jamison, Stéphane Gimenez, 2004-2006) and src/trace/autotrace/inkscape-autotrace.cpp
 * (Marc Jeanmougin, 2018), with the changes made for KanzonasSVG (Keith Lyding, 2026):
 * no GTK, GLib or 2geom, SVG path data written directly. Released under GNU GPL v2+.
 */
#include "kzsvg.h"

#include <algorithm>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <array>
#include <cstdio>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <exception>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "filterset.h"
#include "parallel.h"
#include "imagemap.h"
#include "quantize.h"

extern "C" {
#include "potracelib.h"
#include "bitmap.h"
#include <autotrace/autotrace.h>
#include <autotrace/spline.h>
}

using namespace Inkscape::Trace;

namespace {

char const *const VERSION = "1.0";

struct Cancelled : std::exception {};

// The most path data one trace may write. Random noise or heavy film grain with many colors
// made SVGs of gigabytes (a 0.2-megapixel picture of noise at 256 colors: 220 MB, a bigger one
// filled the memory): past this, the trace stops with a message instead.
constexpr size_t MAX_SVG_BYTES = 500u * 1000 * 1000;

struct TooBig : std::exception
{
    const char *what() const noexcept override
    {
        return "the SVG would be over 500 MB (a very detailed or noisy picture): use fewer colors, "
               "Smooth, or more Speckles";
    }
};

// Path data written by the trace this thread works for (layers run on several threads).
thread_local std::atomic<size_t> *svg_budget = nullptr;

inline void count_bytes(size_t n)
{
    if (svg_budget && (*svg_budget += n) > MAX_SVG_BYTES) {
        throw TooBig();
    }
}

/** Progress reporting: a fraction of the whole job, and a way to stop it. */
class Progress
{
public:
    Progress(kz_progress_func func, void *data)
        : func(func)
        , data(data)
    {}

    // Report <f> (0..1) of the part [from, from + span) of the job.
    void report(double f)
    {
        if (cancel && *cancel) {
            stopped = true;
            throw Cancelled();
        }
        double v = from + span * std::clamp(f, 0.0, 1.0);
        if (!func || v < last + 0.01) {
            if (stopped) {
                throw Cancelled();
            }
            return;
        }
        last = v;
        if (func(v, data)) {
            stopped = true;
            throw Cancelled();
        }
    }

    // Work on the part [from + span*a, from + span*(a + b)) from now on.
    struct Part
    {
        Progress &p;
        double from, span;
        Part(Progress &p, double a, double b)
            : p(p)
            , from(p.from)
            , span(p.span)
        {
            p.from = from + span * a;
            p.span = span * b;
        }
        ~Part()
        {
            p.from = from;
            p.span = span;
        }
    };

    bool stopped = false;
    std::atomic<bool> const *cancel = nullptr; // a layer's: stop when the whole trace stops

private:
    kz_progress_func func;
    void *data;
    double from = 0.0, span = 1.0, last = -1.0;
};

/*
 * Pixels in
 */

// Composite over white (dividing by 255 with rounding: dividing by 256 darkened
// every pixel, so white came out as 254 and no color was exact).
inline unsigned char over_white(int c, int alpha)
{
    return (unsigned char)((c * alpha + 127) / 255 + (255 - alpha));
}

RgbMap to_rgbmap(unsigned char const *rgba, int width, int height, int stride)
{
    auto map = RgbMap(width, height);
    for (int y = 0; y < height; y++) {
        auto p = rgba + (size_t)stride * y;
        auto q = map.row(y);
        for (int x = 0; x < width; x++, p += 4) {
            int a = p[3];
            q[x] = {over_white(p[0], a), over_white(p[1], a), over_white(p[2], a)};
        }
    }
    return map;
}

GrayMap to_graymap(RgbMap const &rgb)
{
    auto map = GrayMap(rgb.width, rgb.height);
    for (size_t i = 0; i < rgb.pixels.size(); i++) {
        auto c = rgb.pixels[i];
        map.pixels[i] = (unsigned long)c.r + c.g + c.b;
    }
    return map;
}

/*
 * SVG out
 */

// A number with up to 3 decimals and no trailing zeros, always with a '.'
// (never the C library's locale-dependent printf: Qt sets the locale).
void put_number(std::string &out, double v)
{
    long long n = std::llround(v * 1000.0);
    if (n < 0) {
        out += '-';
        n = -n;
    }
    long long whole = n / 1000;
    int frac = (int)(n % 1000);
    out += std::to_string(whole);
    if (frac) {
        char digits[5] = {'.', char('0' + frac / 100), char('0' + frac / 10 % 10), char('0' + frac % 10), 0};
        int len = 4;
        while (digits[len - 1] == '0') {
            len--;
        }
        out.append(digits, len);
    }
}

struct PathData
{
    std::string d;
    size_t nodes = 0;
    size_t elements = 0; // points as Qt counts them (a curve is 3): see to_svg()

    void point(double x, double y)
    {
        size_t before = d.size();
        put_number(d, x);
        d += ',';
        put_number(d, y);
        count_bytes(d.size() - before + 1);
    }
    void move(double x, double y)
    {
        d += 'M';
        point(x, y);
        nodes++;
        elements++;
    }
    void line(double x, double y)
    {
        d += 'L';
        point(x, y);
        nodes++;
        elements++;
    }
    void curve(double x1, double y1, double x2, double y2, double x, double y)
    {
        d += 'C';
        point(x1, y1);
        d += ' ';
        point(x2, y2);
        d += ' ';
        point(x, y);
        nodes++;
        elements += 3;
    }
    void close()
    {
        d += 'Z';
        elements++;
    }
    bool empty() const { return d.empty(); }
};

// A shape's outlines in groups: each group an outline with the holes in it (a hole only cuts
// out of an outline in the same <path> element), so a long path can be split between groups.
using Paths = std::vector<PathData>;

struct Shape
{
    std::string style;
    Paths paths;
};

// Shapes from the bottom up.
using Shapes = std::vector<Shape>;

inline int channel_diff(RGB a, RGB b)
{
    return std::max({std::abs(a.r - b.r), std::abs(a.g - b.g), std::abs(a.b - b.b)});
}

std::string hex_color(RGB c)
{
    static char const hexdigits[] = "0123456789abcdef";
    std::string s = "#";
    for (int v : {c.r, c.g, c.b}) {
        s += hexdigits[v >> 4];
        s += hexdigits[v & 15];
    }
    return s;
}

// Points in one <path> element at most. Qt's SVG reader (KanzonasSVG's own view, and other
// Qt programs) stops reading a path at about 32,000 points (QPainterPath elements; a curve
// counts 3): a picture of a few thousand small shapes in one color used to show only part of
// itself. Longer paths are split between groups (an outline and its holes stay together).
constexpr size_t MAX_PATH_ELEMENTS = 20000;

std::string to_svg(Shapes const &shapes, int width, int height, int *npaths)
{
    std::string out = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                      "<!-- Created with KanzonasSVG " +
                      std::string(VERSION) +
                      " -->\n"
                      "<svg xmlns=\"http://www.w3.org/2000/svg\" version=\"1.1\" width=\"" +
                      std::to_string(width) + "\" height=\"" + std::to_string(height) + "\" viewBox=\"0 0 " +
                      std::to_string(width) + " " + std::to_string(height) + "\">\n";
    int count = 0;
    for (auto const &s : shapes) {
        size_t k = 0;
        while (k < s.paths.size()) {
            out += "<path style=\"" + s.style + "\" d=\"";
            size_t elements = 0;
            do {
                out += s.paths[k].d;
                elements += s.paths[k].elements;
                k++;
            } while (k < s.paths.size() && elements + s.paths[k].elements <= MAX_PATH_ELEMENTS);
            out += "\"/>\n";
            count++;
        }
    }
    out += "</svg>\n";
    if (npaths) {
        *npaths = count;
    }
    return out;
}

/*
 * Potrace
 */

struct PotraceParams
{
    potrace_param_t *p = potrace_param_default();
    ~PotraceParams() { potrace_param_free(p); }
};

struct BitmapDeleter
{
    void operator()(potrace_bitmap_t *b) { bm_free(b); }
};
using BitmapPtr = std::unique_ptr<potrace_bitmap_t, BitmapDeleter>;

struct StateDeleter
{
    void operator()(potrace_state_t *s) { potrace_state_free(s); }
};

struct PointHash
{
    size_t operator()(std::pair<double, double> const &p) const
    {
        uint64_t a, b;
        std::memcpy(&a, &p.first, 8);
        std::memcpy(&b, &p.second, 8);
        return std::hash<uint64_t>()(a * 0x9E3779B97F4A7C15ull ^ b);
    }
};
using PointSet = std::unordered_set<std::pair<double, double>, PointHash>;

// Write Potrace's path tree; <points> leaves out paths already written (as Inkscape does).
void write_paths(potrace_path_t *paths, PathData &out, PointSet &points);

// One outline, then the outlines inside it (its holes, and the shapes in those).
void write_path(potrace_path_t *path, PathData &out, PointSet &points)
{
    {
        auto const &curve = path->curve;
        if (curve.n == 0) {
            return;
        }
        auto const &last = curve.c[curve.n - 1][2];
        if (!points.emplace(last.x, last.y).second) {
            return;
        }
        out.move(last.x, last.y);
        for (int i = 0; i < curve.n; i++) {
            auto const *seg = curve.c[i];
            if (curve.tag[i] == POTRACE_CORNER) {
                out.line(seg[1].x, seg[1].y);
                out.line(seg[2].x, seg[2].y);
            } else if (curve.tag[i] == POTRACE_CURVETO) {
                out.curve(seg[0].x, seg[0].y, seg[1].x, seg[1].y, seg[2].x, seg[2].y);
            }
        }
        out.close();
        for (auto child = path->childlist; child; child = child->sibling) {
            write_paths(child, out, points);
        }
    }
}

void write_paths(potrace_path_t *paths, PathData &out, PointSet &points)
{
    for (auto path = paths; path; path = path->sibling) {
        write_path(path, out, points);
    }
}

// Trace a Potrace bitmap (set bits are traced), freeing it.
Paths trace_bitmap(BitmapPtr bitmap, kz_options const &o, Progress &progress)
{
    PotraceParams params;
    params.p->turdsize = o.speckles;
    params.p->alphamax = o.smooth_corners;
    params.p->opticurve = o.optimize;
    params.p->opttolerance = o.optimize_tolerance;
    params.p->progress.callback = [](double f, void *data) {
        try {
            static_cast<Progress *>(data)->report(f);
        } catch (Cancelled const &) {
            // Potrace is C: can't throw through it. report() remembers, and throws again after.
        }
    };
    params.p->progress.data = &progress;
    params.p->progress.min = 0.0;
    params.p->progress.max = 1.0;
    params.p->progress.epsilon = 0.0;

    auto state = std::unique_ptr<potrace_state_t, StateDeleter>(potrace_trace(params.p, bitmap.get()));
    bitmap.reset();
    if (progress.stopped) {
        throw Cancelled();
    }

    Paths out;
    if (!state || state->status != POTRACE_STATUS_OK) {
        return out;
    }
    // each outline at the top, with everything inside it, in a group of its own
    PointSet points;
    for (auto path = state->plist; path; path = path->sibling) {
        PathData group;
        write_path(path, group, points);
        if (!group.empty()) {
            out.push_back(std::move(group));
        }
    }
    return out;
}

BitmapPtr new_bitmap(int w, int h)
{
    auto b = BitmapPtr(bm_new(w, h));
    if (!b) {
        throw std::bad_alloc();
    }
    bm_clear(b.get(), 0);
    return b;
}

Paths trace_graymap(GrayMap const &gm, kz_options const &o, Progress &progress)
{
    auto bitmap = new_bitmap(gm.width, gm.height);
    for (int y = 0; y < gm.height; y++) {
        for (int x = 0; x < gm.width; x++) {
            BM_UPUT(bitmap.get(), x, y, gm.getPixel(x, y) ? 0 : 1);
        }
    }
    return trace_bitmap(std::move(bitmap), o, progress);
}

// Brightness cutoff between <floor> and <cutoff> (fractions), or the edges, as black and white.
GrayMap single_scan(RgbMap const &rgb, kz_options const &o, double floor, double cutoff)
{
    auto gm = to_graymap(rgb);
    GrayMap map(gm.width, gm.height);
    if (o.mode == KZ_EDGES) {
        map = grayMapCanny(gm, 0.1, o.threshold);
    } else {
        double lo = 3.0 * floor * 256.0;
        double hi = 3.0 * cutoff * 256.0;
        for (size_t i = 0; i < gm.pixels.size(); i++) {
            double b = gm.pixels[i];
            map.pixels[i] = b >= lo && b < hi ? GrayMap::BLACK : GrayMap::WHITE;
        }
    }
    if (o.invert && o.mode != KZ_BRIGHTNESS_STEPS) {
        for (auto &p : map.pixels) {
            p = GrayMap::WHITE - p;
        }
    }
    return map;
}

// KZ_PROFILE=1 prints how long each step takes (to stderr).
struct Timer
{
    const char *what;
    std::chrono::steady_clock::time_point t0 = std::chrono::steady_clock::now();
    explicit Timer(const char *w)
        : what(w)
    {}
    ~Timer()
    {
        static const bool on = std::getenv("KZ_PROFILE") != nullptr;
        if (on) {
            std::fprintf(stderr, "kz: %-22s %7.3f s\n", what,
                         std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count());
        }
    }
};

// The palette after quantizing: edge shades dropped and snapped (judged on the image as
// quantized: smoothing keeps edges sharp, and judging on the unsmoothed one brought back the
// noise it removed), the exact colors from the insides of the shapes, and colors that came
// out nearly the same merged (then the edges again, between the colors that are left).
IndexedMap palette(RgbMap const &map, RgbMap const &smoothed, int ncolors, ColorHistogram const *hist = nullptr)
{
    IndexedMap imap(1, 1);
    { Timer t("quantize"); imap = rgbMapQuantize(smoothed, ncolors, hist); }
    { Timer t("drop blend colors"); dropBlendColors(smoothed, imap); }
    { Timer t("snap blended edges"); snapBlendedEdges(smoothed, imap); }
    { Timer t("refine palette"); refinePalette(map, imap); }
    if (mergeDuplicateColors(imap)) {
        dropBlendColors(smoothed, imap);
        snapBlendedEdges(smoothed, imap);
        refinePalette(map, imap);
    }
    return imap;
}

// The colors for multiple scans: edge-preserving smoothing, quantizing, edge shades
// dropped and snapped, then the exact colors from the insides of the shapes.
// A fingerprint of a picture's pixels (FNV-1a over 64-bit words, on several cores): telling
// whether the picture is the one the cached colors were made from.
uint64_t fingerprint(RgbMap const &map)
{
    auto const *bytes = reinterpret_cast<unsigned char const *>(map.pixels.data());
    size_t const n = map.pixels.size() * sizeof(RGB);
    int const parts = 16;
    uint64_t h[parts];
    kz::parallel_for(parts, [&](long b, long e) {
        for (long part = b; part < e; part++) {
            size_t from = n * part / parts, to = n * (part + 1) / parts;
            uint64_t x = 1469598103934665603ull ^ (uint64_t)part;
            size_t i = from;
            for (; i + 8 <= to; i += 8) {
                uint64_t w;
                std::memcpy(&w, bytes + i, 8);
                x = (x ^ w) * 1099511628211ull;
            }
            for (; i < to; i++) {
                x = (x ^ bytes[i]) * 1099511628211ull;
            }
            h[part] = x;
        }
    }, 1);
    uint64_t x = 1469598103934665603ull ^ ((uint64_t)map.width << 32 | (uint64_t)map.height);
    for (auto v : h) {
        x = (x ^ v) * 1099511628211ull;
    }
    return x;
}

// The smoothed picture and its color histogram, kept for the last picture: they depend only
// on the picture and Smooth, so another number of colors starts from them (smoothing a
// 12-megapixel photo took 0.2-0.3 s of the 0.9 s).
struct Prepared
{
    RgbMap smoothed{1, 1};
    ColorHistogram histogram;
};

// The caches hold the last two pictures: the window traces a small copy of a big picture
// first (a quick preview), then the picture itself, and neither should push the other out.
constexpr size_t CACHED_PICTURES = 2;

struct PreparedEntry
{
    uint64_t key;
    int width, height, smooth;
    std::shared_ptr<Prepared const> value;
};

struct PreparedCache
{
    std::mutex m;
    std::deque<PreparedEntry> entries; // newest first
} prepared_cache;

std::shared_ptr<Prepared const> prepared(RgbMap const &map, uint64_t key, bool smooth)
{
    {
        std::lock_guard<std::mutex> lock(prepared_cache.m);
        auto &e = prepared_cache.entries;
        for (size_t i = 0; i < e.size(); i++) {
            if (e[i].key == key && e[i].width == map.width && e[i].height == map.height && e[i].smooth == (int)smooth) {
                auto hit = e[i];
                e.erase(e.begin() + i);
                e.push_front(hit);
                return hit.value;
            }
        }
    }
    auto p = std::make_shared<Prepared>();
    { Timer t("smooth"); p->smoothed = smooth ? rgbMapGaussian(map) : map; }
    { Timer t("histogram"); p->histogram = colorHistogram(p->smoothed); }
    std::lock_guard<std::mutex> lock(prepared_cache.m);
    auto &e = prepared_cache.entries;
    e.push_front({key, map.width, map.height, (int)smooth, p});
    while (e.size() > CACHED_PICTURES) {
        e.pop_back();
    }
    return p;
}

// The last picture's reduced colors, kept: changing only a setting that doesn't change them
// (speckles, smooth corners, optimize, tolerance, stack, background) traces again without
// reducing the colors again (0.7 of the 1 s a 12-megapixel photo took).
struct ColorEntry
{
    uint64_t key;
    int width, height, scans, smooth;
    std::shared_ptr<IndexedMap const> imap;
};

struct ColorCache
{
    std::mutex m;
    std::deque<ColorEntry> entries; // newest first
} color_cache;

IndexedMap quantized(RgbMap const &map, kz_options const &o)
{
    uint64_t const key = fingerprint(map);
    {
        std::lock_guard<std::mutex> lock(color_cache.m);
        auto &e = color_cache.entries;
        auto it = std::find_if(e.begin(), e.end(), [&](ColorEntry const &c) {
            return c.key == key && c.width == map.width && c.height == map.height && c.scans == o.scans &&
                   c.smooth == (int)(o.smooth != 0);
        });
        if (it != e.end()) {
            auto hit = *it;
            e.erase(it);
            e.push_front(hit);
            IndexedMap imap = *hit.imap;
            if (o.mode == KZ_GRAYS) {
                for (auto &col : imap.clut) {
                    unsigned char v = ((int)col.r + col.g + col.b) / 3;
                    col = {v, v, v};
                }
            }
            return imap;
        }
    }
    auto prep = prepared(map, key, o.smooth != 0);
    auto imap = palette(map, prep->smoothed, o.scans, &prep->histogram);
    {
        std::lock_guard<std::mutex> lock(color_cache.m);
        auto &e = color_cache.entries;
        e.push_front({key, map.width, map.height, o.scans, (int)(o.smooth != 0), std::make_shared<IndexedMap const>(imap)});
        while (e.size() > CACHED_PICTURES) {
            e.pop_back();
        }
    }
    if (o.mode == KZ_GRAYS) {
        for (auto &c : imap.clut) {
            unsigned char s = ((int)c.r + c.g + c.b) / 3;
            c = {s, s, s};
        }
    }
    return imap;
}

/**
 * The background: the color that most of the picture's edge has (at least a quarter of
 * it), or -1 when no color does.
 */
int background_index(IndexedMap const &imap)
{
    std::vector<long> count(imap.nrColors, 0);
    long total = 0;
    auto add = [&](int x, int y) {
        unsigned k = imap.pixels[(size_t)y * imap.width + x];
        if ((int)k < imap.nrColors) {
            count[k]++;
        }
        total++;
    };
    for (int x = 0; x < imap.width; x++) {
        add(x, 0);
        add(x, imap.height - 1);
    }
    for (int y = 1; y + 1 < imap.height; y++) {
        add(0, y);
        add(imap.width - 1, y);
    }
    if (!total || imap.nrColors == 0) {
        return -1;
    }
    int best = (int)(std::max_element(count.begin(), count.end()) - count.begin());
    return count[best] * 4 >= total ? best : -1;
}

/**
 * The pixels to leave out: those of the background color <b> that reach the edge of the
 * picture through others of that color (KZ_BG_REMOVE: white inside a logo stays), or all of
 * that color (KZ_BG_REMOVE_ALL).
 */
std::vector<unsigned char> background_mask(IndexedMap const &imap, int b, int how)
{
    int const w = imap.width, h = imap.height;
    std::vector<unsigned char> out((size_t)w * h, 0);
    if (how == KZ_BG_REMOVE_ALL) {
        for (size_t i = 0; i < out.size(); i++) {
            out[i] = (int)imap.pixels[i] == b;
        }
        return out;
    }
    std::vector<size_t> todo;
    auto seed = [&](int x, int y) {
        size_t i = (size_t)y * w + x;
        if (!out[i] && (int)imap.pixels[i] == b) {
            out[i] = 1;
            todo.push_back(i);
        }
    };
    for (int x = 0; x < w; x++) {
        seed(x, 0);
        seed(x, h - 1);
    }
    for (int y = 0; y < h; y++) {
        seed(0, y);
        seed(w - 1, y);
    }
    while (!todo.empty()) {
        size_t i = todo.back();
        todo.pop_back();
        int x = (int)(i % w), y = (int)(i / w);
        if (x > 0) seed(x - 1, y);
        if (x + 1 < w) seed(x + 1, y);
        if (y > 0) seed(x, y - 1);
        if (y + 1 < h) seed(x, y + 1);
    }
    return out;
}

/**
 * Trace <n> independent layers on several cores: layer(k, quiet) gives layer k's paths, quiet
 * being a Progress that reports nothing and stops when the trace is cancelled. This thread
 * traces layers too, and between them reports progress (the caller's callback is only ever
 * called from the thread that called kz_trace) and notices cancelling. The results are in
 * layer order whatever order they finish in: the same SVG as on one core.
 */
template <class Layer>
std::vector<Paths> run_layers(int n, Progress &progress, Layer layer)
{
    std::vector<Paths> out(n);
    std::atomic<int> next{0}, done{0};
    std::atomic<bool> stop{false};
    std::exception_ptr error;
    std::mutex m;
    auto *budget = svg_budget;
    auto work_one = [&](Progress &quiet) {
        int k = next++;
        if (k >= n) {
            return false;
        }
        try {
            out[k] = layer(k, quiet);
        } catch (...) {
            std::lock_guard<std::mutex> lock(m);
            if (!error) {
                error = std::current_exception();
            }
            stop = true;
        }
        done++;
        return true;
    };
    std::vector<std::thread> pool;
    struct Joiner
    {
        std::vector<std::thread> &pool;
        std::atomic<bool> &stop;
        ~Joiner()
        {
            stop = true;
            for (auto &t : pool) {
                t.join();
            }
        }
    } joiner{pool, stop};
    int const extra = std::min(kz::threads(), n) - 1;
    for (int i = 0; i < extra; i++) {
        pool.emplace_back([&, budget] {
            svg_budget = budget;
            Progress quiet(nullptr, nullptr);
            quiet.cancel = &stop;
            while (!stop && work_one(quiet)) {
            }
        });
    }
    Progress quiet(nullptr, nullptr);
    quiet.cancel = &stop;
    while (!stop && work_one(quiet)) {
        progress.report((double)done / n); // throws Cancelled: the joiner stops the others
    }
    for (auto &t : pool) {
        t.join();
    }
    pool.clear();
    if (error) {
        std::rethrow_exception(error);
    }
    progress.report(1.0);
    return out;
}

Shapes trace_colors(RgbMap const &map, kz_options const &o, Progress &progress)
{
    IndexedMap imap(1, 1);
    {
        Progress::Part part(progress, 0.0, 0.15);
        imap = quantized(map, o);
        progress.report(1.0);
    }
    Progress::Part all(progress, 0.15, 0.85);

    // The background left out: its pixels are in no layer, so it shows through.
    int const bg = o.remove_background ? background_index(imap) : -1;
    std::vector<unsigned char> gone;
    if (bg >= 0) {
        gone = background_mask(imap, bg, o.remove_background);
    }

    // Colors with no pixel left (the background color, all of it left out) get no layer:
    // stacked, it would be drawn under the others for nothing.
    std::vector<char> present(imap.nrColors, 0);
    for (size_t i = 0; i < imap.pixels.size(); i++) {
        if (imap.pixels[i] < (unsigned)imap.nrColors && (gone.empty() || !gone[i])) {
            present[imap.pixels[i]] = 1;
        }
    }

    auto layers = run_layers(imap.nrColors, progress, [&](int k, Progress &quiet) -> Paths {
        if (!present[k]) {
            return {};
        }
        // The pixels of this color, and when stacking, those of every color before it.
        auto bitmap = new_bitmap(imap.width, imap.height);
        for (int y = 0; y < imap.height; y++) {
            auto line = bm_scanline(bitmap.get(), y);
            auto src = imap.row(y);
            auto out = gone.empty() ? nullptr : gone.data() + (size_t)y * imap.width;
            for (int x = 0; x < imap.width; x++) {
                int index = src[x];
                if ((o.stack ? index <= k : index == k) && !(out && out[x])) {
                    line[x / BM_WORDBITS] |= bm_mask(x);
                }
            }
        }
        return trace_bitmap(std::move(bitmap), o, quiet);
    });
    Shapes top_down;
    for (int k = 0; k < imap.nrColors; k++) {
        if (!layers[k].empty()) {
            top_down.push_back({"fill:" + hex_color(imap.clut[k]), std::move(layers[k])});
        }
    }
    return {std::make_move_iterator(top_down.rbegin()), std::make_move_iterator(top_down.rend())};
}

Shapes trace_brightness_steps(RgbMap const &map, kz_options const &o, Progress &progress)
{
    double constexpr low = 0.2, high = 0.9;
    double const delta = (high - low) / o.scans;

    // step i: from <floor> (0, or when tiling, the step before's cutoff) to its cutoff
    auto cutoff = [&](int i) { return low + delta * i; };
    auto layers = run_layers(o.scans, progress, [&](int i, Progress &quiet) {
        double floor = o.stack || i == 0 ? 0.0 : cutoff(i - 1);
        return trace_graymap(single_scan(map, o, floor, cutoff(i)), o, quiet);
    });
    Shapes top_down;
    for (int i = 0; i < o.scans; i++) {
        if (!layers[i].empty()) {
            unsigned char v = (unsigned char)std::min(255.0, 256.0 * cutoff(i));
            top_down.push_back({"fill:" + hex_color({v, v, v}), std::move(layers[i])});
        }
    }
    if (top_down.size() > 1 && o.remove_background) {
        top_down.pop_back();
    }
    return {std::make_move_iterator(top_down.rbegin()), std::make_move_iterator(top_down.rend())};
}

Shapes trace_single(RgbMap const &map, kz_options const &o, Progress &progress)
{
    GrayMap gm(1, 1);
    {
        Progress::Part part(progress, 0.0, 0.2);
        gm = single_scan(map, o, 0.0, o.threshold);
    }
    Progress::Part part(progress, 0.2, 0.8);
    Shapes shapes;
    auto path = trace_graymap(gm, o, progress);
    if (!path.empty()) {
        shapes.push_back({"fill:#000000", std::move(path)});
    }
    return shapes;
}

/*
 * Autotrace
 */

int autotrace_colors(kz_options const &o)
{
    // As Inkscape's dialog: the background is one of the colors.
    return o.mode == KZ_CENTERLINE ? 2 : std::min(256, o.scans + 1);
}

/**
 * Reduce the colors with the quantizer above instead of Autotrace's own: edge-preserving
 * smoothing, exact colors, and none of the in-between shades of anti-aliased edges, which
 * Autotrace traced as thousands of thin fragments around every shape. A palette color
 * within a few levels of white becomes exactly white, which Autotrace leaves out (white
 * with JPEG noise, for example). Only that close: Autotrace cuts background areas out of
 * the regions around them, and the regions under those show through, so a light color made
 * background turned white areas into holes.
 */
RgbMap autotrace_input(RgbMap const &map, kz_options const &o, RGB *background = nullptr)
{
    auto prep = prepared(map, fingerprint(map), true);
    auto imap = palette(map, prep->smoothed, autotrace_colors(o), &prep->histogram);

    // The color Autotrace leaves out: white, or the picture's background when it is removed.
    RGB bg = {255, 255, 255};
    if (o.remove_background) {
        int b = background_index(imap);
        if (b >= 0) {
            bg = imap.clut[b];
        }
    }
    if (background) {
        *background = bg;
    }
    constexpr int NEAR_BACKGROUND = 10; // levels per channel
    for (int k = 0; k < imap.nrColors; k++) {
        auto &c = imap.clut[k];
        if (channel_diff(c, bg) <= NEAR_BACKGROUND) {
            c = bg;
        }
    }

    RgbMap out(map.width, map.height);
    for (size_t i = 0; i < out.pixels.size(); i++) {
        out.pixels[i] = imap.clut[imap.pixels[i] % imap.clut.size()];
    }
    return out;
}

struct Box
{
    double x0, y0, x1, y1;
    bool valid = false;
    void add(double x, double y)
    {
        if (!valid) {
            x0 = x1 = x;
            y0 = y1 = y;
            valid = true;
        } else {
            x0 = std::min(x0, x);
            x1 = std::max(x1, x);
            y0 = std::min(y0, y);
            y1 = std::max(y1, y);
        }
    }
    void add(Box const &b)
    {
        if (b.valid) {
            add(b.x0, b.y0);
            add(b.x1, b.y1);
        }
    }
    bool contains(Box const &b) const
    {
        return valid && b.valid && x0 <= b.x0 && b.x1 <= x1 && y0 <= b.y0 && b.y1 <= y1;
    }
    bool intersects(Box const &b) const
    {
        return valid && b.valid && x0 <= b.x1 && b.x0 <= x1 && y0 <= b.y1 && b.y0 <= y1;
    }
};

struct SplinesDeleter
{
    void operator()(at_splines_type *s) { at_splines_free(s); }
};
struct OptsDeleter
{
    void operator()(at_fitting_opts_type *p) { at_fitting_opts_free(p); }
};

Shapes trace_autotrace(RgbMap const &map, kz_options const &o, Progress &progress)
{
    autotrace_init();

    RgbMap input(1, 1);
    RGB background = {255, 255, 255};
    {
        Progress::Part part(progress, 0.0, 0.2);
        input = autotrace_input(map, o, &background);
        progress.report(1.0);
    }

    auto opts = std::unique_ptr<at_fitting_opts_type, OptsDeleter>(at_fitting_opts_new());
    at_color white = {background.r, background.g, background.b};
    opts->background_color = &white;
    opts->color_count = 0; // already reduced
    opts->centerline = o.mode == KZ_CENTERLINE;
    opts->preserve_width = o.preserve_width;
    opts->filter_iterations = o.filter_iterations;
    opts->error_threshold = (gfloat)o.error_threshold;

    at_bitmap bitmap;
    bitmap.width = input.width;
    bitmap.height = input.height;
    bitmap.np = 3;
    static_assert(sizeof(RGB) == 3);
    bitmap.bitmap = reinterpret_cast<unsigned char *>(input.pixels.data());

    std::unique_ptr<at_splines_type, SplinesDeleter> splines;
    {
        Progress::Part part(progress, 0.2, 0.7);
        splines.reset(at_splines_new_full(
            &bitmap, opts.get(), nullptr, nullptr,
            [](gfloat f, gpointer data) {
                try {
                    static_cast<Progress *>(data)->report(f);
                } catch (Cancelled const &) {
                }
            },
            &progress, [](gpointer data) -> gboolean { return static_cast<Progress *>(data)->stopped; }, &progress));
    }
    opts->background_color = nullptr; // not Autotrace's to free
    if (progress.stopped) {
        throw Cancelled();
    }
    if (!splines) {
        return {};
    }

    Progress::Part part(progress, 0.9, 0.1);
    double const height = splines->height;
    auto px = [&](at_real_coord const &c) { return c.x; };
    auto py = [&](at_real_coord const &c) { return height - c.y; };

    // Autotrace's regions are drawn in order, each over the ones before it, and only
    // background areas are cut out of them: the outline of such a hole (the inside of
    // an O) comes as an outline of its own, of the region's color, running the other
    // way. It only makes a hole when it is in the same path as the outline around it,
    // so each hole joins the path of the latest region of its color around it.
    // Outlines join the latest path of their style if nothing drawn after it overlaps
    // them: drawn lower down, it looks the same, with far fewer objects.
    struct Item
    {
        Shape shape;
        Box box;
    };
    struct Outer
    {
        std::string style;
        Box box;
        size_t item, group; // its outline group in that item: its holes go there too
    };
    std::deque<Item> items;
    std::vector<Outer> outers;

    int const n = SPLINE_LIST_ARRAY_LENGTH(*splines);
    for (int list_i = 0; list_i < n; list_i++) {
        if (list_i % 256 == 0) {
            progress.report((double)list_i / n);
        }
        auto const &list = SPLINE_LIST_ARRAY_ELT(*splines, list_i);
        if (SPLINE_LIST_LENGTH(list) == 0) {
            continue;
        }
        bool const closed = !(splines->centerline || list.open);
        RGB color = {list.color.r, list.color.g, list.color.b};
        std::string style = closed ? "fill:" + hex_color(color) + ";stroke:none"
                                   : "fill:none;stroke:" + hex_color(color);

        Box box;
        box.add(px(START_POINT(SPLINE_LIST_ELT(list, 0))), py(START_POINT(SPLINE_LIST_ELT(list, 0))));
        for (int i = 0; i < SPLINE_LIST_LENGTH(list); i++) {
            auto const spline = SPLINE_LIST_ELT(list, i);
            box.add(px(END_POINT(spline)), py(END_POINT(spline)));
            if (SPLINE_DEGREE(spline) != AT_LINEARTYPE) {
                box.add(px(CONTROL1(spline)), py(CONTROL1(spline)));
                box.add(px(CONTROL2(spline)), py(CONTROL2(spline)));
            }
        }

        Item *item = nullptr;
        PathData *group = nullptr;
        if (closed && list.clockwise) {
            // A hole: the latest region of the same style whose box holds it.
            for (auto it = outers.rbegin(); it != outers.rend(); ++it) {
                if (it->style == style && it->box.contains(box)) {
                    item = &items[it->item];
                    group = &item->shape.paths[it->group];
                    break;
                }
            }
        }
        if (!item) {
            size_t index = items.size();
            for (size_t k = items.size(); k-- > 0;) {
                if (items[k].shape.style == style) {
                    index = k;
                    break;
                }
                if (items[k].box.intersects(box)) {
                    break;
                }
            }
            if (index == items.size()) {
                items.push_back({{style, {}}, {}});
            }
            item = &items[index];
            item->shape.paths.emplace_back();
            group = &item->shape.paths.back();
            if (closed && !list.clockwise) {
                outers.push_back({style, box, index, item->shape.paths.size() - 1});
            }
        }
        item->box.add(box);

        auto &d = *group;
        auto const first = SPLINE_LIST_ELT(list, 0);
        d.move(px(START_POINT(first)), py(START_POINT(first)));
        for (int i = 0; i < SPLINE_LIST_LENGTH(list); i++) {
            auto const spline = SPLINE_LIST_ELT(list, i);
            if (SPLINE_DEGREE(spline) == AT_LINEARTYPE) {
                d.line(px(END_POINT(spline)), py(END_POINT(spline)));
            } else {
                d.curve(px(CONTROL1(spline)), py(CONTROL1(spline)), px(CONTROL2(spline)), py(CONTROL2(spline)),
                        px(END_POINT(spline)), py(END_POINT(spline)));
            }
        }
        if (closed) {
            d.close();
        }
    }

    // In Autotrace's drawing order: bottom first.
    Shapes shapes;
    for (auto &it : items) {
        shapes.push_back(std::move(it.shape));
    }
    return shapes;
}

kz_options checked(kz_options const *in)
{
    kz_options o;
    kz_default_options(&o);
    if (in) {
        // Take what the caller's (possibly older, smaller) struct has.
        int n = std::clamp(in->size, 0, (int)sizeof(kz_options));
        std::memcpy(&o, in, n);
        o.size = sizeof(kz_options);
    }
    // Not-a-number or infinite settings (a caller's mistake, or "nan" typed on the command
    // line) take the default: clamping passes NaN through, and it then broke the scans.
    kz_options d;
    kz_default_options(&d);
    for (auto [v, def] : {std::pair{&o.threshold, d.threshold}, std::pair{&o.smooth_corners, d.smooth_corners},
                          std::pair{&o.optimize_tolerance, d.optimize_tolerance},
                          std::pair{&o.error_threshold, d.error_threshold}}) {
        if (!std::isfinite(*v)) {
            *v = def;
        }
    }
    o.scans = std::clamp(o.scans, 2, 256);
    o.remove_background = std::clamp(o.remove_background, 0, 2);
    o.threshold = std::clamp(o.threshold, 0.0, 1.0);
    o.speckles = std::clamp(o.speckles, 0, 100000);
    o.smooth_corners = std::clamp(o.smooth_corners, 0.0, 1.34);
    o.optimize_tolerance = std::clamp(o.optimize_tolerance, 0.0, 5.0);
    o.error_threshold = std::clamp(o.error_threshold, 0.1, 10.0);
    o.filter_iterations = std::clamp(o.filter_iterations, 0, 20);
    return o;
}

char *dup_string(std::string const &s)
{
    auto p = static_cast<char *>(std::malloc(s.size() + 1));
    if (p) {
        std::memcpy(p, s.c_str(), s.size() + 1);
    }
    return p;
}

bool valid_image(unsigned char const *rgba, int width, int height, int stride)
{
    return rgba && width > 0 && height > 0 && stride >= width * 4 && (long long)width * height <= 400000000LL;
}

/*
 * Recommended settings
 */

// The picture made smaller (box average) to at most about <max_pixels>, for analysis.
RgbMap shrink(RgbMap const &map, long long max_pixels, int &factor)
{
    factor = 1;
    while ((long long)(map.width / factor) * (map.height / factor) > max_pixels) {
        factor++;
    }
    if (factor == 1) {
        return map;
    }
    RgbMap out(std::max(1, map.width / factor), std::max(1, map.height / factor));
    int const n = factor * factor;
    for (int y = 0; y < out.height; y++) {
        for (int x = 0; x < out.width; x++) {
            int r = 0, g = 0, b = 0;
            for (int dy = 0; dy < factor; dy++) {
                auto row = map.row(y * factor + dy) + x * factor;
                for (int dx = 0; dx < factor; dx++) {
                    r += row[dx].r;
                    g += row[dx].g;
                    b += row[dx].b;
                }
            }
            out.pixels[(size_t)y * out.width + x] = {(unsigned char)(r / n), (unsigned char)(g / n),
                                                    (unsigned char)(b / n)};
        }
    }
    return out;
}

struct AutoResult
{
    kz_options o;
    kz_auto_info info;
};

/**
 * Pick settings for a picture: how many colors it needs (the fewest after which more
 * colors no longer make the flat areas visibly closer to the picture), smoothing if it's
 * noisy (JPEG, scans), the background left out if it's transparent, and black and white
 * for a picture of dark gray on light gray (a scan of text or a drawing).
 */
AutoResult choose_settings(unsigned char const *rgba, int width, int height, int stride)
{
    AutoResult res;
    kz_default_options(&res.o);
    std::memset(&res.info, 0, sizeof(res.info));
    res.info.size = sizeof(kz_auto_info);

    // Transparent parts?
    long long clear = 0;
    for (int y = 0; y < height; y++) {
        auto p = rgba + (size_t)stride * y + 3;
        for (int x = 0; x < width; x++, p += 4) {
            clear += *p < 250;
        }
    }
    res.info.transparent = clear * 100 > (long long)width * height; // over 1%

    auto full = to_rgbmap(rgba, width, height, stride);
    int factor = 1;
    auto map = shrink(full, 400000, factor);
    int const w = map.width, h = map.height;

    // Flat pixels: none of the four neighbors differs by more than a little (edges, including
    // soft anti-aliased ones, are left out: whichever side they go to is right).
    constexpr int FLAT = 24;
    std::vector<unsigned char> flat((size_t)w * h, 0);
    long long nflat = 0, nnoisy = 0;
    for (int y = 1; y + 1 < h; y++) {
        for (int x = 1; x + 1 < w; x++) {
            size_t i = (size_t)y * w + x;
            auto c = map.pixels[i];
            int d = std::max({channel_diff(c, map.pixels[i - 1]), channel_diff(c, map.pixels[i + 1]),
                              channel_diff(c, map.pixels[i - w]), channel_diff(c, map.pixels[i + w])});
            if (d <= FLAT) {
                flat[i] = 1;
                nflat++;
            }
        }
    }
    // Noise, on the full-size picture (shrinking averages it away): flat pixels that differ
    // a little from a neighbor. A clean logo's flat areas are exactly one color.
    long long sampled = 0;
    int const step = std::max(1, factor);
    for (int y = 1; y + 1 < full.height; y += step) {
        for (int x = 1; x + 1 < full.width; x += step) {
            size_t i = (size_t)y * full.width + x;
            auto c = full.pixels[i];
            int d = std::max({channel_diff(c, full.pixels[i - 1]), channel_diff(c, full.pixels[i + 1]),
                              channel_diff(c, full.pixels[i - full.width]),
                              channel_diff(c, full.pixels[i + full.width])});
            if (d <= FLAT) {
                sampled++;
                nnoisy += d > 0;
            }
        }
    }
    res.info.noisy = sampled > 0 && nnoisy * 20 > sampled; // over 5% of flat pixels
    res.o.smooth = res.info.noisy;

    // How many colors: the wrong part of the flat areas at 2, 3, ... colors.
    auto smoothed = res.o.smooth ? rgbMapGaussian(map) : map;
    // (up to 16 for any picture; a flat one with more colors, up to 64: see below)
    constexpr int MAX_COLORS = 16;
    constexpr int MAX_FLAT_COLORS = 64; // (the window's Colors setting goes up to 64)
    constexpr int WRONG = 32;           // levels: visibly another color
    std::vector<double> wrong(MAX_FLAT_COLORS + 1, 1.0);
    std::vector<std::array<RGB, 2>> two(1);
    int chosen = 0;
    int actual_at[MAX_FLAT_COLORS + 1] = {0};
    // The counts are tried a few at a time on several cores (each try is independent), then
    // judged in order, so the first count that does is the one picked, as when tried one by one.
    auto hist = colorHistogram(smoothed);
    int const batch = std::max(1, kz::threads());
    auto try_counts = [&](int from, int to, double limit) {
    for (int first = from; first <= to && !chosen; first += batch) {
        int const last = std::min(to, first + batch - 1);
        std::vector<int> kept(MAX_FLAT_COLORS + 1, 0);
        std::vector<std::array<RGB, 2>> two_of(MAX_FLAT_COLORS + 1);
        kz::parallel_for(last - first + 1, [&](long b, long e) {
            for (long k = b; k < e; k++) {
                int n = first + (int)k;
                auto imap = palette(map, smoothed, n, &hist);
                long long bad = 0;
                for (size_t i = 0; i < flat.size(); i++) {
                    if (flat[i] && channel_diff(imap.clut[imap.pixels[i]], map.pixels[i]) > WRONG) {
                        bad++;
                    }
                }
                wrong[n] = nflat ? (double)bad / nflat : 0.0;
                kept[n] = imap.nrColors;
                two_of[n] = {imap.clut[0], imap.clut[std::min(1, imap.nrColors - 1)]};
            }
        }, 1);
        for (int n = first; n <= last; n++) {
            actual_at[n] = kept[n];
            if (n == 2) {
                two[0] = two_of[2];
            }
            if (std::getenv("KZ_AUTO_DEBUG")) {
                std::fprintf(stderr, "auto: %2d colors (%2d kept): %.4f wrong\n", n, kept[n], wrong[n]);
            }
            if (kept[n] < n && wrong[n] <= limit) {
                // the picture has no more colors to give
                chosen = kept[n];
                break;
            }
            if (wrong[n] <= limit) {
                chosen = n;
                break;
            }
        }
    }
    };
    try_counts(2, MAX_COLORS, 0.002);
    // A flat picture (an illustration, a logo, a map) with more than 16 colors: its flat areas
    // are a few exact colors, where a photo's or painting's are thousands of near ones. Count the
    // colors that cover the flat areas; if a few dozen cover them all, try up to that many (a
    // photo never gets here: it's never flat enough, and costs no more than before).
    if (!chosen && !res.info.noisy && nflat > 0) {
        std::unordered_map<uint32_t, long long> counts;
        for (size_t i = 0; i < flat.size() && counts.size() <= 4096; i++) {
            if (flat[i]) {
                auto c = map.pixels[i];
                counts[((uint32_t)c.r << 16) | ((uint32_t)c.g << 8) | c.b]++;
            }
        }
        if (counts.size() <= 4096) {
            // significant: at least 1/2000 of the flat area (a blend at a corner isn't a color)
            long long const least = std::max<long long>(8, nflat / 2000);
            long long covered = 0;
            int significant = 0;
            for (auto const &kv : counts) {
                if (kv.second >= least) {
                    significant++;
                    covered += kv.second;
                }
            }
            if (significant > MAX_COLORS && significant <= MAX_FLAT_COLORS && covered * 1000 >= nflat * 995) {
                // (a few more than counted: the counting and the quantizer don't split colors
                // quite alike.) Stricter than up to 16: no color of the significant ones may go
                // (each is at least 1/2000 of the flat area; up to 16, a small one could).
                try_counts(MAX_COLORS + 1, std::min(MAX_FLAT_COLORS, significant + 4), 0.0002);
                if (!chosen) {
                    // never exact even so: the count that came closest
                    chosen = MAX_COLORS + 1;
                    for (int n = MAX_COLORS + 1; n <= std::min(MAX_FLAT_COLORS, significant + 4); n++) {
                        if (wrong[n] < wrong[chosen]) {
                            chosen = n;
                        }
                    }
                }
            }
        }
    }
    if (!chosen) {
        // Never exact (a photo, a painting, gradients): the fewest colors that get nine
        // tenths of the way from 2 colors to 16 (more add file size for little to see).
        res.info.photo = 1;
        double target = wrong[MAX_COLORS] + 0.10 * (wrong[2] - wrong[MAX_COLORS]);
        chosen = MAX_COLORS;
        for (int n = 2; n <= MAX_COLORS; n++) {
            if (wrong[n] <= target) {
                chosen = n;
                break;
            }
        }
    }
    chosen = std::max(2, chosen);
    res.o.scans = chosen;
    res.info.colors = chosen;
    res.info.wrong = wrong[std::min(chosen, MAX_FLAT_COLORS)];
    if (actual_at[chosen] && actual_at[chosen] < chosen) {
        res.info.wrong = 0.0;
    }

    // Dark gray on light gray: black and white (one shape, no background).
    if (chosen == 2) {
        auto sat = [](RGB c) { return std::max({c.r, c.g, c.b}) - std::min({c.r, c.g, c.b}); };
        auto lum = [](RGB c) { return ((int)c.r + c.g + c.b) / 3; };
        RGB dark = two[0][0], light = two[0][1];
        if (sat(dark) <= 40 && sat(light) <= 40 && lum(dark) <= 110 && lum(light) >= 170) {
            res.o.mode = KZ_BRIGHTNESS;
            res.o.threshold = (lum(dark) + lum(light)) / 2.0 / 256.0;
        }
    }
    // A transparent background stays transparent.
    res.o.remove_background = res.info.transparent && res.o.mode == KZ_COLORS ? KZ_BG_REMOVE : KZ_BG_KEEP;
    return res;
}

} // namespace

extern "C" {

void kz_default_options(kz_options *o)
{
    if (!o) {
        return;
    }
    std::memset(o, 0, sizeof(*o));
    o->size = sizeof(kz_options);
    o->mode = KZ_COLORS;
    o->scans = 8;
    o->smooth = 1;
    o->stack = 1;
    o->remove_background = 0;
    o->threshold = 0.45;
    o->invert = 0;
    o->speckles = 2;
    o->smooth_corners = 1.0;
    o->optimize = 1;
    o->optimize_tolerance = 0.2;
    o->error_threshold = 2.0;
    o->filter_iterations = 4;
    o->preserve_width = 1;
}

int kz_trace(unsigned char const *rgba, int width, int height, int stride, kz_options const *options,
             kz_progress_func progress_func, void *progress_data, char **svg, int *nshapes, char **error)
{
    if (svg) {
        *svg = nullptr;
    }
    if (error) {
        *error = nullptr;
    }
    if (nshapes) {
        *nshapes = 0;
    }
    auto fail = [&](char const *msg, int status) {
        if (error) {
            *error = dup_string(msg);
        }
        return status;
    };
    if (!svg) {
        return fail("no place for the result", KZ_ERROR);
    }
    if (!valid_image(rgba, width, height, stride)) {
        return fail("not a usable image (empty, or over 400 megapixels)", KZ_ERROR);
    }
    try {
        auto o = checked(options);
        Progress progress(progress_func, progress_data);
        auto map = to_rgbmap(rgba, width, height, stride);
        std::atomic<size_t> bytes{0};
        svg_budget = &bytes;
        struct Reset { ~Reset() { svg_budget = nullptr; } } reset;
        Shapes shapes;
        switch (o.mode) {
            case KZ_GRAYS:
            case KZ_COLORS:
                shapes = trace_colors(map, o, progress);
                break;
            case KZ_BRIGHTNESS_STEPS:
                shapes = trace_brightness_steps(map, o, progress);
                break;
            case KZ_BRIGHTNESS:
            case KZ_EDGES:
                shapes = trace_single(map, o, progress);
                break;
            case KZ_AUTOTRACE:
            case KZ_CENTERLINE:
                shapes = trace_autotrace(map, o, progress);
                break;
            default:
                return fail("unknown mode", KZ_ERROR);
        }
        if (progress_func && progress_func(1.0, progress_data)) {
            return fail("cancelled", KZ_CANCELLED);
        }
        int npaths = 0;
        *svg = dup_string(to_svg(shapes, width, height, &npaths));
        if (!*svg) {
            return fail("out of memory", KZ_ERROR);
        }
        if (nshapes) {
            *nshapes = npaths;
        }
        return KZ_OK;
    } catch (Cancelled const &) {
        return fail("cancelled", KZ_CANCELLED);
    } catch (std::bad_alloc const &) {
        return fail("out of memory", KZ_ERROR);
    } catch (std::exception const &e) {
        return fail(e.what(), KZ_ERROR);
    }
}

int kz_preview(unsigned char const *rgba, int width, int height, int stride, kz_options const *options,
               unsigned char *rgb_out)
{
    if (!rgb_out || !valid_image(rgba, width, height, stride)) {
        return KZ_ERROR;
    }
    try {
        auto o = checked(options);
        auto map = to_rgbmap(rgba, width, height, stride);
        auto put = [&](size_t i, RGB c) {
            rgb_out[3 * i] = c.r;
            rgb_out[3 * i + 1] = c.g;
            rgb_out[3 * i + 2] = c.b;
        };
        switch (o.mode) {
            case KZ_COLORS:
            case KZ_GRAYS: {
                auto imap = quantized(map, o);
                for (size_t i = 0; i < imap.pixels.size(); i++) {
                    put(i, imap.clut[imap.pixels[i] % imap.clut.size()]);
                }
                break;
            }
            case KZ_AUTOTRACE:
            case KZ_CENTERLINE: {
                auto in = autotrace_input(map, o);
                for (size_t i = 0; i < in.pixels.size(); i++) {
                    put(i, in.pixels[i]);
                }
                break;
            }
            case KZ_BRIGHTNESS_STEPS:
            case KZ_BRIGHTNESS:
            case KZ_EDGES: {
                // Brightness steps: the middle step, as an idea of what is traced.
                double cutoff = o.mode == KZ_BRIGHTNESS_STEPS ? 0.55 : o.threshold;
                auto gm = single_scan(map, o, 0.0, cutoff);
                for (size_t i = 0; i < gm.pixels.size(); i++) {
                    unsigned char v = (unsigned char)(gm.pixels[i] / 3);
                    put(i, {v, v, v});
                }
                break;
            }
            default:
                return KZ_ERROR;
        }
        return KZ_OK;
    } catch (...) {
        return KZ_ERROR;
    }
}

int kz_auto(unsigned char const *rgba, int width, int height, int stride, kz_options *o, kz_auto_info *info)
{
    if (!o || !valid_image(rgba, width, height, stride)) {
        return KZ_ERROR;
    }
    try {
        auto res = choose_settings(rgba, width, height, stride);
        *o = res.o;
        if (info) {
            int n = std::clamp(info->size, 0, (int)sizeof(kz_auto_info));
            res.info.size = n;
            std::memcpy(info, &res.info, n);
        }
        return KZ_OK;
    } catch (...) {
        return KZ_ERROR;
    }
}

void kz_free(void *p)
{
    std::free(p);
}

char const *kz_version(void)
{
    return VERSION;
}

} // extern "C"
