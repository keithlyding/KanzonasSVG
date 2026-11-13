// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Drawing KanzonasSVG's own SVGs for the window, fast and off Python's lock.
 *
 * Qt's SVG renderer holds Python's global lock while it draws (0.3-0.4 s for the SVG of a
 * photo), so the window froze at every zoom and every new result, whatever thread drew it.
 * This draws the SVGs the engine writes (paths of M/L/C/Z, each filled with a color or, for
 * centerlines, stroked) into a premultiplied ARGB32 buffer, as Qt's QImage holds it. It is
 * called through ctypes, which lets go of the lock.
 *
 * Anti-aliasing by accumulated signed area (as font rasterizers such as font-rs do): each
 * line adds the area it covers to the cells of its rows, a running sum along each row gives
 * the winding at every pixel, and min(1, |winding|) is the pixel's coverage (the nonzero rule
 * the SVGs use: holes run the other way). Curves are flattened to lines finer than a tenth of
 * a pixel. Rows are split between cores.
 */
#include "kzsvg.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "parallel.h"

namespace {

struct Seg
{
    float x0, y0, x1, y1; // in the SVG's viewBox units
};

struct Shape
{
    unsigned char r, g, b;
    bool stroke;          // a centerline (stroked, 1 unit wide), else filled
    std::vector<Seg> segs; // closed outlines (filled) or the line itself (stroked)
    float minx, miny, maxx, maxy;
};

struct Drawing
{
    double vbw = 0, vbh = 0; // viewBox size
    std::vector<Shape> shapes;
};

bool parse_number(char const *&p, double &v)
{
    while (*p == ' ' || *p == ',' || *p == '\n' || *p == '\t') {
        p++;
    }
    char *end;
    v = std::strtod(p, &end);
    if (end == p) {
        return false;
    }
    p = end;
    return true;
}

// Path data of M, L, C and Z (absolute), as the engine writes it.
void parse_path(char const *p, char const *end, Shape &s)
{
    double cx = 0, cy = 0, sx = 0, sy = 0;
    bool open = false;
    auto line = [&](double x, double y) {
        s.segs.push_back({(float)cx, (float)cy, (float)x, (float)y});
        cx = x;
        cy = y;
    };
    auto close = [&] {
        if (open && (cx != sx || cy != sy)) {
            line(sx, sy);
        }
        open = false;
    };
    char cmd = 0;
    while (p < end) {
        while (p < end && (*p == ' ' || *p == ',')) {
            p++;
        }
        if (p >= end) {
            break;
        }
        if (std::strchr("MLCZ", *p)) {
            cmd = *p++;
            if (cmd == 'Z') {
                if (!s.stroke) {
                    close();
                } else if (open) {
                    line(sx, sy);
                }
                continue;
            }
        }
        double v[6];
        int need = cmd == 'C' ? 6 : 2;
        if (cmd != 'M' && cmd != 'L' && cmd != 'C') {
            return; // not ours
        }
        for (int i = 0; i < need; i++) {
            if (!parse_number(p, v[i])) {
                return;
            }
        }
        if (cmd == 'M') {
            if (!s.stroke) {
                close();
            }
            cx = sx = v[0];
            cy = sy = v[1];
            open = true;
            cmd = 'L'; // more pairs after M are lines
        } else if (cmd == 'L') {
            line(v[0], v[1]);
        } else {
            // flattened finely enough for any zoom (redone in pixel units when drawing would be
            // better, but the SVG's units are pixels of the picture, and 64x zoom at most)
            double x0 = cx, y0 = cy;
            double len = std::hypot(v[0] - x0, v[1] - y0) + std::hypot(v[2] - v[0], v[3] - v[1]) +
                         std::hypot(v[4] - v[2], v[5] - v[3]);
            int n = std::clamp((int)std::ceil(std::sqrt(len * 8.0)), 2, 256);
            for (int i = 1; i <= n; i++) {
                double t = (double)i / n, u = 1 - t;
                double x = u * u * u * x0 + 3 * u * u * t * v[0] + 3 * u * t * t * v[2] + t * t * t * v[4];
                double y = u * u * u * y0 + 3 * u * u * t * v[1] + 3 * u * t * t * v[3] + t * t * t * v[5];
                line(x, y);
            }
        }
    }
    if (!s.stroke) {
        close();
    }
}

int hex2(char const *p)
{
    char buf[3] = {p[0], p[1], 0};
    return (int)std::strtol(buf, nullptr, 16);
}

Drawing *parse(char const *svg)
{
    auto d = new Drawing;
    std::string text(svg);
    size_t vb = text.find("viewBox=\"");
    if (vb != std::string::npos) {
        char const *p = text.c_str() + vb + 9;
        double x, y;
        parse_number(p, x);
        parse_number(p, y);
        parse_number(p, d->vbw);
        parse_number(p, d->vbh);
    }
    size_t pos = 0;
    while ((pos = text.find("<path ", pos)) != std::string::npos) {
        size_t endTag = text.find("/>", pos);
        if (endTag == std::string::npos) {
            break;
        }
        std::string style;
        size_t st = text.find("style=\"", pos);
        if (st != std::string::npos && st < endTag) {
            style = text.substr(st + 7, text.find('"', st + 7) - st - 7);
        }
        Shape s{};
        size_t f = style.find("fill:#"), k = style.find("stroke:#");
        if (f != std::string::npos) {
            s.r = hex2(&style[f + 6]);
            s.g = hex2(&style[f + 8]);
            s.b = hex2(&style[f + 10]);
        } else if (k != std::string::npos) {
            s.stroke = true;
            s.r = hex2(&style[k + 8]);
            s.g = hex2(&style[k + 10]);
            s.b = hex2(&style[k + 12]);
        } else {
            pos = endTag;
            continue;
        }
        size_t dd = text.find(" d=\"", pos);
        if (dd != std::string::npos && dd < endTag) {
            size_t de = text.find('"', dd + 4);
            parse_path(text.c_str() + dd + 4, text.c_str() + de, s);
        }
        if (!s.segs.empty()) {
            s.minx = s.miny = 1e30f;
            s.maxx = s.maxy = -1e30f;
            for (auto const &g : s.segs) {
                s.minx = std::min({s.minx, g.x0, g.x1});
                s.maxx = std::max({s.maxx, g.x0, g.x1});
                s.miny = std::min({s.miny, g.y0, g.y1});
                s.maxy = std::max({s.maxy, g.y0, g.y1});
            }
            d->shapes.push_back(std::move(s));
        }
        pos = endTag;
    }
    return d;
}

/**
 * Adds the line (pixel coordinates) to the cells of the rows [r0, r1) it crosses; acc holds
 * rows of w + 2 cells, its first row being row <base>.
 */
void add_line(std::vector<float> &acc, int w, int base, int r0, int r1, float x0, float y0, float x1, float y1)
{
    if (y0 == y1) {
        return;
    }
    float dir = 1;
    if (y0 > y1) {
        std::swap(x0, x1);
        std::swap(y0, y1);
        dir = -1;
    }
    if (y1 <= r0 || y0 >= r1) {
        return;
    }
    float const dxdy = (x1 - x0) / (y1 - y0);
    float x = x0;
    if (y0 < r0) {
        x += (r0 - y0) * dxdy;
        y0 = (float)r0;
    }
    int const ystart = (int)std::floor(y0), yend = std::min(r1, (int)std::ceil(y1));
    float const W = (float)w;
    for (int y = ystart; y < yend; y++) {
        float dy = std::min((float)(y + 1), y1) - std::max((float)y, y0);
        float xnext = x + dxdy * dy;
        float d = dy * dir;
        float *row = acc.data() + (size_t)(y - base) * (w + 2);
        // within the area: left of it counts at its left edge, right of it not at all
        float a = std::clamp(x, 0.0f, W), b = std::clamp(xnext, 0.0f, W);
        float lo = std::min(a, b), hi = std::max(a, b);
        float lofl = std::floor(lo);
        int loi = (int)lofl;
        int hii = (int)std::ceil(hi);
        if (hii <= loi + 1) {
            float xm = 0.5f * (a + b) - lofl;
            row[loi] += d - d * xm;
            row[loi + 1] += d * xm;
        } else {
            float s = 1.0f / (hi - lo);
            float x0f = lo - lofl;
            float a0 = 0.5f * s * (1 - x0f) * (1 - x0f);
            float x1f = hi - (float)hii + 1;
            float am = 0.5f * s * x1f * x1f;
            row[loi] += d * a0;
            if (hii == loi + 2) {
                row[loi + 1] += d * (1 - a0 - am);
            } else {
                float a1 = s * (1.5f - x0f);
                row[loi + 1] += d * (a1 - a0);
                for (int xi = loi + 2; xi < hii - 1; xi++) {
                    row[xi] += d * s;
                }
                float a2 = a1 + (float)(hii - loi - 3) * s;
                row[hii - 1] += d * (1 - a2 - am);
            }
            row[hii] += d * am;
        }
        x = xnext;
    }
}

void render_rows(Drawing const &dr, unsigned char *out, int w, int stride, int r0, int r1, double sx, double sy,
                 double ox, double oy)
{
    int const rows = r1 - r0;
    std::vector<float> acc((size_t)rows * (w + 2));
    for (auto const &s : dr.shapes) {
        // rows this shape touches, in this band
        double half = s.stroke ? 0.5 * std::max(sx, sy) + 1 : 1;
        int y0 = std::max(r0, (int)std::floor(s.miny * sy + oy - half));
        int y1 = std::min(r1, (int)std::ceil(s.maxy * sy + oy + half));
        if (y0 >= y1 || s.minx * sx + ox - half >= w) {
            continue; // above, below or right of this band (left of it still covers it)
        }
        std::fill(acc.begin() + (size_t)(y0 - r0) * (w + 2), acc.begin() + (size_t)(y1 - r0) * (w + 2), 0.0f);
        if (!s.stroke) {
            for (auto const &g : s.segs) {
                add_line(acc, w, r0, y0, y1, (float)(g.x0 * sx + ox), (float)(g.y0 * sy + oy), (float)(g.x1 * sx + ox),
                         (float)(g.y1 * sy + oy));
            }
        } else {
            // a stroke 1 unit wide: each segment as a quad, all turning the same way
            double hw = 0.5;
            for (auto const &g : s.segs) {
                double dx = g.x1 - g.x0, dy = g.y1 - g.y0, len = std::hypot(dx, dy);
                if (len == 0) {
                    continue;
                }
                double nx = -dy / len * hw, ny = dx / len * hw;
                float px[4] = {(float)((g.x0 + nx) * sx + ox), (float)((g.x1 + nx) * sx + ox),
                               (float)((g.x1 - nx) * sx + ox), (float)((g.x0 - nx) * sx + ox)};
                float py[4] = {(float)((g.y0 + ny) * sy + oy), (float)((g.y1 + ny) * sy + oy),
                               (float)((g.y1 - ny) * sy + oy), (float)((g.y0 - ny) * sy + oy)};
                for (int i = 0; i < 4; i++) {
                    add_line(acc, w, r0, y0, y1, px[i], py[i], px[(i + 1) % 4], py[(i + 1) % 4]);
                }
            }
        }
        // the running sum along each row is the winding; composite the color over the buffer
        float const cr = s.r, cg = s.g, cb = s.b;
        for (int y = y0; y < y1; y++) {
            float *row = acc.data() + (size_t)(y - r0) * (w + 2);
            unsigned char *px = out + (size_t)y * stride;
            float sum = 0;
            for (int x = 0; x < w; x++) {
                sum += row[x];
                float c = std::min(1.0f, std::fabs(sum));
                if (c <= 0.0005f) {
                    continue;
                }
                unsigned char *q = px + 4 * x; // B, G, R, A (premultiplied, little-endian ARGB32)
                float keep = 1 - c;
                q[0] = (unsigned char)(cb * c + q[0] * keep + 0.5f);
                q[1] = (unsigned char)(cg * c + q[1] * keep + 0.5f);
                q[2] = (unsigned char)(cr * c + q[2] * keep + 0.5f);
                q[3] = (unsigned char)(255 * c + q[3] * keep + 0.5f);
            }
        }
    }
}

} // namespace

extern "C" {

void *kz_drawing_open(const char *svg)
{
    if (!svg) {
        return nullptr;
    }
    try {
        return parse(svg);
    } catch (...) {
        return nullptr;
    }
}

void kz_drawing_close(void *drawing)
{
    delete static_cast<Drawing *>(drawing);
}

int kz_drawing_render(void *drawing, unsigned char *out, int width, int height, int stride, double left, double top,
                      double target_width, double target_height)
{
    auto dr = static_cast<Drawing *>(drawing);
    if (!dr || !out || width <= 0 || height <= 0 || stride < width * 4 || dr->vbw <= 0 || dr->vbh <= 0 ||
        !(target_width > 0) || !(target_height > 0)) {
        return KZ_ERROR;
    }
    try {
        double sx = target_width / dr->vbw, sy = target_height / dr->vbh;
        // bands of rows on several cores (each band draws every shape over its rows only)
        kz::parallel_for(height, [&](long r0, long r1) {
            render_rows(*dr, out, width, stride, (int)r0, (int)r1, sx, sy, left, top);
        }, 16);
        return KZ_OK;
    } catch (...) {
        return KZ_ERROR;
    }
}

} // extern "C"
