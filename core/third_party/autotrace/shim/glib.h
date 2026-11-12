/* SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The few GLib definitions Autotrace's tracing code uses, so that it builds with
 * no GLib (KanzonasSVG uses Autotrace only to trace a bitmap in memory: none of
 * its input or output modules, which are the parts that need more of GLib).
 */
#ifndef KANZONASSVG_GLIB_SHIM_H
#define KANZONASSVG_GLIB_SHIM_H

#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int gboolean;
typedef char gchar;
typedef unsigned char guchar;
typedef int gint;
typedef unsigned int guint;
typedef unsigned short gushort;
typedef unsigned char guint8;
typedef float gfloat;
typedef double gdouble;
typedef void *gpointer;
typedef const void *gconstpointer;
typedef unsigned int GQuark;
typedef unsigned long GType;

#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

#ifdef _WIN32
#define G_DIR_SEPARATOR '\\'
#else
#define G_DIR_SEPARATOR '/'
#endif

typedef struct _GError {
    GQuark domain;
    gint code;
    gchar *message;
} GError;

typedef void (*GDestroyNotify)(gpointer data);
typedef gpointer (*GBoxedCopyFunc)(gpointer boxed);
typedef void (*GBoxedFreeFunc)(gpointer boxed);

#define g_return_if_fail(expr) do { if (!(expr)) return; } while (0)
#define g_return_val_if_fail(expr, val) do { if (!(expr)) return (val); } while (0)
#define g_assert_not_reached() abort()

#define g_malloc(n) malloc(n)
#define g_free(p) free(p)
#define g_new(type, n) ((type *)malloc(sizeof(type) * (size_t)(n)))

static inline gchar *g_strdup(const gchar *s)
{
    if (!s) return NULL;
    size_t n = strlen(s) + 1;
    gchar *d = (gchar *)malloc(n);
    if (d) memcpy(d, s, n);
    return d;
}

static inline GQuark g_quark_from_static_string(const gchar *s)
{
    (void)s;
    return 1;
}

static inline GType g_boxed_type_register_static(const gchar *name, GBoxedCopyFunc copy, GBoxedFreeFunc free_func)
{
    (void)name; (void)copy; (void)free_func;
    return 1;
}

/* Errors only come from parsing color strings, which KanzonasSVG never does: dropped. */
#define g_set_error(err, domain, code, ...) do { if (err) *(err) = NULL; } while (0)
#define g_propagate_error(dest, src) do { if (dest) *(dest) = (src); } while (0)

#ifdef __cplusplus
}
#endif

#endif
