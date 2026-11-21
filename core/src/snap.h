// Snapping traced outlines to the shapes they were drawn as (kz_options.snap):
// - an outline within half a pixel (0.4% of the radius, when bigger) of an ellipse with level
//   axes becomes that ellipse
//   (a circle when its two radii are within 2% of each other), as four exact arcs;
// - a curve within half a pixel, and 1.5% of its length, of the straight line between its ends
//   becomes that line, and lines that go on in the same direction become one;
// - a line within about 1.5 degrees of level or upright becomes exactly level or upright (the
//   points it shares with the lines and curves beside it move with it; a curve keeps the
//   direction it leaves a moved point in).
// Potrace's outlines only (Autotrace's are left as they are). Each outline on its own: a hole
// stays a hole (an outline keeps the direction it went round in).

#pragma once

#include <algorithm>
#include <cmath>
#include <numeric>
#include <vector>

namespace kzsnap {

constexpr double PI = 3.14159265358979323846; // (M_PI isn't in Visual Studio's <cmath> by default)

struct Pt
{
    double x, y;
};

inline Pt operator+(Pt a, Pt b) { return {a.x + b.x, a.y + b.y}; }
inline Pt operator-(Pt a, Pt b) { return {a.x - b.x, a.y - b.y}; }
inline Pt operator*(Pt a, double k) { return {a.x * k, a.y * k}; }

// A line (c1, c2 unused) or a cubic curve from p0 to p1. In an outline, each piece starts
// where the one before ends, and the last ends where the first starts.
struct Seg
{
    bool curve;
    Pt p0, c1, c2, p1;
};

enum { LINES = 1, RIGHT_ANGLES = 2, CIRCLES = 4, ALL = 7 };

inline Pt at(Seg const &s, double t)
{
    if (!s.curve) {
        return s.p0 + (s.p1 - s.p0) * t;
    }
    double u = 1 - t;
    return s.p0 * (u * u * u) + s.c1 * (3 * u * u * t) + s.c2 * (3 * u * t * t) + s.p1 * (t * t * t);
}

inline double dist_to_line(Pt p, Pt a, Pt b)
{
    Pt d = b - a;
    double len = std::hypot(d.x, d.y);
    if (len < 1e-12) {
        return std::hypot(p.x - a.x, p.y - a.y);
    }
    return std::fabs((p.x - a.x) * d.y - (p.y - a.y) * d.x) / len;
}

// where p falls along a->b: 0 at a, 1 at b
inline double along(Pt p, Pt a, Pt b)
{
    Pt d = b - a;
    double l2 = d.x * d.x + d.y * d.y;
    return l2 < 1e-24 ? 0.0 : ((p.x - a.x) * d.x + (p.y - a.y) * d.y) / l2;
}

inline double signed_area(std::vector<Pt> const &pts)
{
    double a = 0;
    for (size_t i = 0, n = pts.size(); i < n; i++) {
        Pt p = pts[i], q = pts[(i + 1) % n];
        a += p.x * q.y - q.x * p.y;
    }
    return a / 2;
}

inline std::vector<Pt> samples(std::vector<Seg> const &segs, int per)
{
    std::vector<Pt> pts;
    pts.reserve(segs.size() * per);
    for (auto const &s : segs) {
        for (int k = 0; k < per; k++) {
            pts.push_back(at(s, (double)k / per));
        }
    }
    return pts;
}

// Solve the 4x4 system m x = r (Gaussian elimination with pivoting); false if singular.
inline bool solve4(double m[4][4], double r[4], double x[4])
{
    for (int c = 0; c < 4; c++) {
        int piv = c;
        for (int i = c + 1; i < 4; i++) {
            if (std::fabs(m[i][c]) > std::fabs(m[piv][c])) piv = i;
        }
        if (std::fabs(m[piv][c]) < 1e-14) return false;
        std::swap(m[c], m[piv]);
        std::swap(r[c], r[piv]);
        for (int i = c + 1; i < 4; i++) {
            double f = m[i][c] / m[c][c];
            for (int j = c; j < 4; j++) m[i][j] -= f * m[c][j];
            r[i] -= f * r[c];
        }
    }
    for (int i = 3; i >= 0; i--) {
        double v = r[i];
        for (int j = i + 1; j < 4; j++) v -= m[i][j] * x[j];
        x[i] = v / m[i][i];
    }
    return true;
}

// How far p is from the ellipse (center cx, cy, radii a, b), along the line to its center.
inline double off_ellipse(Pt p, double cx, double cy, double a, double b)
{
    double dx = p.x - cx, dy = p.y - cy;
    double d = std::hypot(dx, dy);
    if (d < 1e-9) {
        return -std::min(a, b);
    }
    double c = dx / d, sn = dy / d;
    return d - a * b / std::sqrt(b * b * c * c + a * a * sn * sn);
}

// Least squares on off_ellipse (a circle: a = b), from the start given.
inline void refine(std::vector<Pt> const &pts, double &cx, double &cy, double &a, double &b, bool circle)
{
    int np = circle ? 3 : 4;
    for (int iter = 0; iter < 10; iter++) {
        double v[4] = {cx, cy, a, circle ? a : b};
        auto f = [&](double const *q, Pt p) { return off_ellipse(p, q[0], q[1], q[2], circle ? q[2] : q[3]); };
        double jtj[4][4] = {}, jtr[4] = {};
        for (Pt p : pts) {
            double r0 = f(v, p), j[4];
            for (int k = 0; k < np; k++) {
                double w[4] = {v[0], v[1], v[2], v[3]};
                double h = 1e-4 * std::max(1.0, std::fabs(w[k]));
                w[k] += h;
                j[k] = (f(w, p) - r0) / h;
            }
            for (int r = 0; r < np; r++) {
                jtr[r] -= j[r] * r0;
                for (int c = 0; c < np; c++) jtj[r][c] += j[r] * j[c];
            }
        }
        if (circle) {               // (a 3x3 system in a 4x4 one)
            jtj[3][3] = 1;
            jtr[3] = 0;
        }
        double step[4];
        if (!solve4(jtj, jtr, step)) return;
        cx += step[0];
        cy += step[1];
        a += step[2];
        b = circle ? a : b + step[3];
        if (std::fabs(step[0]) + std::fabs(step[1]) + std::fabs(step[2]) + std::fabs(step[3]) < 1e-6) return;
    }
}

// The outline as an ellipse with level axes, if it is one: replaces segs and returns true.
inline bool snap_ellipse(std::vector<Seg> &segs)
{
    if (segs.size() < 2) {
        return false;
    }
    std::vector<Pt> pts = samples(segs, 8);
    // centered and scaled first (the fit's numbers stay near 1)
    Pt mid{0, 0};
    for (Pt p : pts) mid = mid + p;
    mid = mid * (1.0 / pts.size());
    double scale = 0;
    for (Pt p : pts) scale = std::max(scale, std::hypot(p.x - mid.x, p.y - mid.y));
    if (scale < 2.5) {
        return false;              // (a dot: nothing to gain)
    }
    // A x^2 + C y^2 + D x + E y = 1, least squares
    double m[4][4] = {}, r[4] = {};
    for (Pt p : pts) {
        double x = (p.x - mid.x) / scale, y = (p.y - mid.y) / scale;
        double v[4] = {x * x, y * y, x, y};
        for (int i = 0; i < 4; i++) {
            r[i] += v[i];
            for (int j = 0; j < 4; j++) m[i][j] += v[i] * v[j];
        }
    }
    double s[4];
    if (!solve4(m, r, s) || s[0] <= 0 || s[1] <= 0) {
        return false;
    }
    double A = s[0], C = s[1], D = s[2], E = s[3];
    double cx = -D / (2 * A), cy = -E / (2 * C);
    double k = 1 + D * D / (4 * A) + E * E / (4 * C);
    if (k <= 0) {
        return false;
    }
    double a = std::sqrt(k / A) * scale, b = std::sqrt(k / C) * scale;
    cx = cx * scale + mid.x;
    cy = cy * scale + mid.y;
    if (std::min(a, b) < 2.0 || std::max(a, b) > 50 * std::min(a, b)) {
        return false;
    }
    bool circle = std::fabs(a - b) <= 0.02 * std::max(a, b);
    if (circle) {
        a = b = (a + b) / 2;
    }
    // That fit (on the equation) leans a few tenths of a pixel off on a big circle; refine it on
    // the points' own distances from the ellipse (Gauss-Newton, a few steps).
    refine(pts, cx, cy, a, b, circle);
    // every point of the outline near it: within half a pixel, or 0.4% of the radius when big
    // (Potrace follows a drawn circle within a few tenths of a pixel at any size)
    double tol = std::max(0.5, 0.004 * std::min(a, b));
    for (Pt p : pts) {
        double dx = p.x - cx, dy = p.y - cy;
        double d = std::hypot(dx, dy);
        if (d < 1e-9) return false;
        double c = dx / d, sn = dy / d;
        double rr = a * b / std::sqrt(b * b * c * c + a * a * sn * sn);
        if (std::fabs(d - rr) > tol) return false;
    }
    // and going round once, enclosing the ellipse's area (not a figure eight, not a C)
    double area = signed_area(pts);
    if (std::fabs(std::fabs(area) - PI * a * b) > 0.03 * PI * a * b) {
        return false;
    }
    // four arcs, in the direction the outline went round
    const double K = 0.5522847498307936;   // 4/3 (sqrt(2) - 1)
    Pt E0{cx + a, cy}, S0{cx, cy + b}, W0{cx - a, cy}, N0{cx, cy - b};
    std::vector<Seg> out;
    if (area > 0) {                         // (y down: right, bottom, left, top)
        out = {{true, E0, {cx + a, cy + K * b}, {cx + K * a, cy + b}, S0},
               {true, S0, {cx - K * a, cy + b}, {cx - a, cy + K * b}, W0},
               {true, W0, {cx - a, cy - K * b}, {cx - K * a, cy - b}, N0},
               {true, N0, {cx + K * a, cy - b}, {cx + a, cy - K * b}, E0}};
    } else {
        out = {{true, E0, {cx + a, cy - K * b}, {cx + K * a, cy - b}, N0},
               {true, N0, {cx - K * a, cy - b}, {cx - a, cy - K * b}, W0},
               {true, W0, {cx - a, cy + K * b}, {cx - K * a, cy + b}, S0},
               {true, S0, {cx + K * a, cy + b}, {cx + a, cy + K * b}, E0}};
    }
    segs.swap(out);
    return true;
}

// Curves that are (all but) straight become lines; lines going on in one direction, one line.
inline void snap_lines(std::vector<Seg> &segs)
{
    for (auto &s : segs) {
        if (!s.curve) continue;
        double len = std::hypot(s.p1.x - s.p0.x, s.p1.y - s.p0.y);
        if (len < 1e-9) continue;
        // how far the curve strays from the chord: at most 3/4 of its control points' distance
        // (a short curve that strays a little is a real bend: within 1.5% of its length too)
        double d = 0.75 * std::max(dist_to_line(s.c1, s.p0, s.p1), dist_to_line(s.c2, s.p0, s.p1));
        double t1 = along(s.c1, s.p0, s.p1), t2 = along(s.c2, s.p0, s.p1);
        if (d <= 0.5 && d <= 0.015 * len && t1 > -0.05 && t1 < 1.05 && t2 > -0.05 && t2 < 1.05) {
            s.curve = false;
        }
    }
    // join: two lines, the point between them near the line from the first's start to the
    // second's end (and between them): within 0.35 pixels, and 3% of their length (a step or
    // a cut corner between short lines stays)
    bool joined = true;
    while (joined && segs.size() > 3) {
        joined = false;
        for (size_t i = 0; i < segs.size() && segs.size() > 3; i++) {
            size_t j = (i + 1) % segs.size();
            Seg &s = segs[i], &n = segs[j];
            if (s.curve || n.curve) continue;
            double t = along(s.p1, s.p0, n.p1);
            double d = dist_to_line(s.p1, s.p0, n.p1);
            double len = std::hypot(n.p1.x - s.p0.x, n.p1.y - s.p0.y);
            if (t > 0 && t < 1 && d <= 0.35 && d <= 0.03 * len) {
                s.p1 = n.p1;
                segs.erase(segs.begin() + j);
                if (j < i) i--;         // (the first piece went: s moved down one)
                joined = true;
            }
        }
    }
}

struct Groups
{
    std::vector<size_t> up;
    explicit Groups(size_t n) : up(n) { std::iota(up.begin(), up.end(), 0); }
    size_t find(size_t a) { return up[a] == a ? a : up[a] = find(up[a]); }
    void join(size_t a, size_t b) { up[find(a)] = find(b); }
};

// Lines (all but) level or upright made exactly so: the points they join share one y (level)
// or x (upright).
inline void snap_right_angles(std::vector<Seg> &segs)
{
    size_t n = segs.size();
    if (n < 2) return;
    // point i: where segs[i] starts (and segs[i-1] ends)
    std::vector<Pt> pt(n);
    for (size_t i = 0; i < n; i++) pt[i] = segs[i].p0;
    Groups level(n), upright(n);
    std::vector<bool> on_level(n, false), on_upright(n, false);
    const double slope = std::tan(1.5 * PI / 180);
    for (size_t i = 0; i < n; i++) {
        Seg const &s = segs[i];
        if (s.curve) continue;
        size_t j = (i + 1) % n;
        double dx = std::fabs(s.p1.x - s.p0.x), dy = std::fabs(s.p1.y - s.p0.y);
        if (dx > 1e-9 && dy <= dx * slope && dy <= 4.0) {
            level.join(i, j);
            on_level[i] = on_level[j] = true;
        } else if (dy > 1e-9 && dx <= dy * slope && dx <= 4.0) {
            upright.join(i, j);
            on_upright[i] = on_upright[j] = true;
        }
    }
    std::vector<double> sum_y(n, 0), sum_x(n, 0), cnt_y(n, 0), cnt_x(n, 0);
    for (size_t i = 0; i < n; i++) {
        if (on_level[i]) {
            size_t g = level.find(i);
            sum_y[g] += pt[i].y;
            cnt_y[g]++;
        }
        if (on_upright[i]) {
            size_t g = upright.find(i);
            sum_x[g] += pt[i].x;
            cnt_x[g]++;
        }
    }
    std::vector<Pt> moved(n, Pt{0, 0});
    for (size_t i = 0; i < n; i++) {
        Pt np = pt[i];
        if (on_level[i]) {
            size_t g = level.find(i);
            np.y = sum_y[g] / cnt_y[g];
        }
        if (on_upright[i]) {
            size_t g = upright.find(i);
            np.x = sum_x[g] / cnt_x[g];
        }
        moved[i] = np - pt[i];
        pt[i] = np;
    }
    for (size_t i = 0; i < n; i++) {
        size_t j = (i + 1) % n;
        Seg &s = segs[i];
        s.p0 = pt[i];
        s.p1 = pt[j];
        if (s.curve) {              // (the curve leaves a moved point in the same direction)
            s.c1 = s.c1 + moved[i];
            s.c2 = s.c2 + moved[j];
        }
    }
}

inline void snap(std::vector<Seg> &segs, int what)
{
    if ((what & CIRCLES) && snap_ellipse(segs)) {
        return;
    }
    if (what & LINES) {
        snap_lines(segs);
    }
    if (what & RIGHT_ANGLES) {
        snap_right_angles(segs);
    }
}

} // namespace kzsnap
