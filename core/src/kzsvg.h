// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * KanzonasSVG engine: trace a bitmap into an SVG.
 *
 * A plain C interface, so that the app (Python, through ctypes) and anything else
 * can call it. The tracing is Inkscape's Trace Bitmap (Potrace and Autotrace), with
 * the quality and speed fixes made for KanzonasSVG; see README.md.
 */
#ifndef KANZONASSVG_KZSVG_H
#define KANZONASSVG_KZSVG_H

#ifdef _WIN32
#define KZ_API __declspec(dllexport)
#else
#define KZ_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* What to trace (Inkscape's Trace Bitmap modes). */
enum kz_mode {
    KZ_COLORS = 0,           /* Potrace, multiple scans: colors */
    KZ_GRAYS = 1,            /* Potrace, multiple scans: grays */
    KZ_BRIGHTNESS_STEPS = 2, /* Potrace, multiple scans: brightness steps */
    KZ_BRIGHTNESS = 3,       /* Potrace, single scan: brightness cutoff */
    KZ_EDGES = 4,            /* Potrace, single scan: edge detection */
    KZ_AUTOTRACE = 5,        /* Autotrace, colors */
    KZ_CENTERLINE = 6        /* Autotrace, centerline (strokes along the middle of lines) */
};

/* Version of this struct: set kz_options.size to sizeof(kz_options). */
typedef struct kz_options {
    int size;               /* sizeof(kz_options) */
    int mode;               /* enum kz_mode */
    int scans;              /* colors / grays / steps (multiple scans and Autotrace), 2..256 */
    int smooth;             /* multiple scans: edge-preserving smoothing first (1/0) */
    int stack;              /* multiple scans: stack scans (1) or tile them (0) */
    int remove_background;  /* multiple scans: leave out the bottom (background) layer */
    double threshold;       /* brightness cutoff (0..1), edge detection threshold (0..1) */
    int invert;             /* single scan: trace the light parts instead */
    int speckles;           /* Potrace: drop shapes of up to this many pixels */
    double smooth_corners;  /* Potrace: corner threshold, 0 (sharp) .. 1.34 */
    int optimize;           /* Potrace: join curve segments (1/0) */
    double optimize_tolerance; /* Potrace: how far joining may move the curve, 0..5 */
    double error_threshold; /* Autotrace: fitting error, in pixels */
    int filter_iterations;  /* Autotrace: smoothing passes on outlines */
    int preserve_width;     /* Autotrace centerline: keep line widths (1/0) */
} kz_options;

/* Fill <o> with the defaults (Inkscape's Trace Bitmap dialog defaults). */
KZ_API void kz_default_options(kz_options *o);

/* Called now and then with the fraction done (0..1). Return 0 to go on, anything else to stop. */
typedef int (*kz_progress_func)(double fraction, void *data);

/* Results of kz_trace. */
enum kz_status { KZ_OK = 0, KZ_CANCELLED = 1, KZ_ERROR = 2 };

/*
 * Trace an 8-bit RGBA image (non-premultiplied; transparent parts count as white),
 * <stride> bytes from one row to the next. On KZ_OK, *svg is a complete SVG document
 * (UTF-8, NUL-terminated): free it with kz_free. *nshapes, if given, gets the number
 * of <path> elements. On other results *svg is NULL and *error (if given) a message,
 * also freed with kz_free.
 */
KZ_API int kz_trace(const unsigned char *rgba, int width, int height, int stride, const kz_options *o,
                    kz_progress_func progress, void *progress_data, char **svg, int *nshapes, char **error);

/*
 * The image as it will be traced (colors reduced, or the black-and-white scan),
 * written to <rgb_out>: width*height*3 bytes, packed RGB. Returns KZ_OK or KZ_ERROR.
 */
KZ_API int kz_preview(const unsigned char *rgba, int width, int height, int stride, const kz_options *o,
                      unsigned char *rgb_out);

KZ_API void kz_free(void *p);

/* The engine's version, for example "1.0". */
KZ_API const char *kz_version(void);

#ifdef __cplusplus
}
#endif

#endif
