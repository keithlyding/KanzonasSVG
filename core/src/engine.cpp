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
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <exception>
#include <memory>
#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include "filterset.h"
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

    void point(double x, double y)
    {
        put_number(d, x);
        d += ',';
        put_number(d, y);
    }
    void move(double x, double y)
    {
        d += 'M';
        point(x, y);
        nodes++;
    }
    void line(double x, double y)
    {
        d += 'L';
        point(x, y);
        nodes++;
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
    }
    void close() { d += 'Z'; }
    bool empty() const { return d.empty(); }
};

struct Shape
{
    std::string style;
    PathData path;
};

// Shapes from the bottom up.
using Shapes = std::vector<Shape>;

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

std::string to_svg(Shapes const &shapes, int width, int height)
{
    std::string out = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                      "<!-- Created with KanzonasSVG " +
                      std::string(VERSION) +
                      " -->\n"
                      "<svg xmlns=\"http://www.w3.org/2000/svg\" version=\"1.1\" width=\"" +
                      std::to_string(width) + "\" height=\"" + std::to_string(height) + "\" viewBox=\"0 0 " +
                      std::to_string(width) + " " + std::to_string(height) + "\">\n";
    for (auto const &s : shapes) {
        out += "<path style=\"" + s.style + "\" d=\"" + s.path.d + "\"/>\n";
    }
    out += "</svg>\n";
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
void write_paths(potrace_path_t *paths, PathData &out, PointSet &points)
{
    for (auto path = paths; path; path = path->sibling) {
        auto const &curve = path->curve;
        if (curve.n == 0) {
            continue;
        }
        auto const &last = curve.c[curve.n - 1][2];
        if (!points.emplace(last.x, last.y).second) {
            continue;
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

// Trace a Potrace bitmap (set bits are traced), freeing it.
PathData trace_bitmap(BitmapPtr bitmap, kz_options const &o, Progress &progress)
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

    PathData out;
    if (!state || state->status != POTRACE_STATUS_OK) {
        return out;
    }
    PointSet points;
    write_paths(state->plist, out, points);
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

PathData trace_graymap(GrayMap const &gm, kz_options const &o, Progress &progress)
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

// The colors for multiple scans: edge-preserving smoothing, quantizing, edge shades
// dropped and snapped, then the exact colors from the insides of the shapes.
IndexedMap quantized(RgbMap const &map, kz_options const &o)
{
    auto smoothed = o.smooth ? rgbMapGaussian(map) : map;
    auto imap = rgbMapQuantize(smoothed, o.scans);
    // Anti-aliased edges, judged on the image as quantized: smoothing keeps edges
    // sharp, and judging on the unsmoothed one brought back the noise it removed.
    dropBlendColors(smoothed, imap);
    snapBlendedEdges(smoothed, imap);
    refinePalette(map, imap);
    if (o.mode == KZ_GRAYS) {
        for (auto &c : imap.clut) {
            unsigned char s = ((int)c.r + c.g + c.b) / 3;
            c = {s, s, s};
        }
    }
    return imap;
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

    Shapes top_down;
    for (int k = 0; k < imap.nrColors; k++) {
        Progress::Part part(progress, (double)k / imap.nrColors, 1.0 / imap.nrColors);
        // The pixels of this color, and when stacking, those of every color before it.
        auto bitmap = new_bitmap(imap.width, imap.height);
        for (int y = 0; y < imap.height; y++) {
            auto line = bm_scanline(bitmap.get(), y);
            auto src = imap.row(y);
            for (int x = 0; x < imap.width; x++) {
                int index = src[x];
                if (o.stack ? index <= k : index == k) {
                    line[x / BM_WORDBITS] |= bm_mask(x);
                }
            }
        }
        auto path = trace_bitmap(std::move(bitmap), o, progress);
        if (!path.empty()) {
            top_down.push_back({"fill:" + hex_color(imap.clut[k]), std::move(path)});
        }
    }
    // The last scan (holding every pixel when stacking) is the background.
    if (top_down.size() > 1 && o.remove_background) {
        top_down.pop_back();
    }
    return {std::make_move_iterator(top_down.rbegin()), std::make_move_iterator(top_down.rend())};
}

Shapes trace_brightness_steps(RgbMap const &map, kz_options const &o, Progress &progress)
{
    double constexpr low = 0.2, high = 0.9;
    double const delta = (high - low) / o.scans;
    double floor = 0.0;

    Shapes top_down;
    for (int i = 0; i < o.scans; i++) {
        Progress::Part part(progress, (double)i / o.scans, 1.0 / o.scans);
        double cutoff = low + delta * i;
        auto path = trace_graymap(single_scan(map, o, floor, cutoff), o, progress);
        if (!path.empty()) {
            unsigned char v = (unsigned char)std::min(255.0, 256.0 * cutoff);
            top_down.push_back({"fill:" + hex_color({v, v, v}), std::move(path)});
        }
        if (!o.stack) {
            floor = cutoff;
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
RgbMap autotrace_input(RgbMap const &map, kz_options const &o)
{
    auto smoothed = rgbMapGaussian(map);
    auto imap = rgbMapQuantize(smoothed, autotrace_colors(o));
    dropBlendColors(smoothed, imap);
    snapBlendedEdges(smoothed, imap);
    refinePalette(map, imap);

    constexpr int NEAR_BACKGROUND = 10; // levels per channel
    for (int k = 0; k < imap.nrColors; k++) {
        auto &c = imap.clut[k];
        if (c.r >= 255 - NEAR_BACKGROUND && c.g >= 255 - NEAR_BACKGROUND && c.b >= 255 - NEAR_BACKGROUND) {
            c = {255, 255, 255};
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
    {
        Progress::Part part(progress, 0.0, 0.2);
        input = autotrace_input(map, o);
        progress.report(1.0);
    }

    auto opts = std::unique_ptr<at_fitting_opts_type, OptsDeleter>(at_fitting_opts_new());
    at_color white = {255, 255, 255};
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
        size_t item;
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
        if (closed && list.clockwise) {
            // A hole: the latest region of the same style whose box holds it.
            for (auto it = outers.rbegin(); it != outers.rend(); ++it) {
                if (it->style == style && it->box.contains(box)) {
                    item = &items[it->item];
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
            if (closed && !list.clockwise) {
                outers.push_back({style, box, index});
            }
        }
        item->box.add(box);

        auto &d = item->shape.path;
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
    o.scans = std::clamp(o.scans, 2, 256);
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
        *svg = dup_string(to_svg(shapes, width, height));
        if (!*svg) {
            return fail("out of memory", KZ_ERROR);
        }
        if (nshapes) {
            *nshapes = (int)shapes.size();
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

void kz_free(void *p)
{
    std::free(p);
}

char const *kz_version(void)
{
    return VERSION;
}

} // extern "C"
