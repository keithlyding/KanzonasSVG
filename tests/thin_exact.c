/* The faster thinning (core/third_party/autotrace/src/autotrace/thin-image.c) against the
   original one (tests/thin_reference.c), pixel for pixel, on random pictures: solid blocks,
   thin lines, noise, one to three colors, 1 to 90 pixels wide and high. Then that cancelling
   stops it at once. Built and run by tests/test_thinning.py:
   thin_exact TRIALS SEED, exit 1 on any difference. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define thin_image thin_image_reference
#define thin3 thin3_reference
#define thin1 thin1_reference
#define masks masks_reference
#define todelete todelete_reference
#define background background_reference
#include "thin_reference.c"
#undef thin_image
#undef thin3
#undef thin1
#undef masks
#undef todelete
#undef background
#undef PIXEL_SET
#undef PIXEL_EQUAL
#define Pixel Pixel_new
#include "thin-image.c"

static unsigned rs = 1;

static unsigned rnd(void)
{
  rs = rs * 1103515245u + 12345u;
  return (rs >> 8) & 0xffffff;
}

static int cancel_after = -1, calls = 0;

static gboolean test_cancel(gpointer data)
{
  (void)data;
  calls++;
  return cancel_after >= 0 && calls > cancel_after;
}

int main(int argc, char **argv)
{
  int trials = argc > 1 ? atoi(argv[1]) : 1000, t, bad = 0;
  static unsigned char colors[4][3] = { {255, 255, 255}, {0, 0, 0}, {200, 30, 40}, {20, 40, 220} };
  rs = argc > 2 ? (unsigned)atoi(argv[2]) : 1;
  for (t = 0; t < trials; t++) {
    int w = 1 + rnd() % (t % 3 ? 40 : 90), h = 1 + rnd() % (t % 3 ? 40 : 90), x, y, k;
    int ncolors = 1 + rnd() % 3, kind = rnd() % 4, size = w * h * 3;
    unsigned char *a = malloc(size), *b = malloc(size);
    at_color bg = { 255, 255, 255 };
    at_exception_type e1 = at_exception_new(NULL, NULL), e2 = at_exception_new(NULL, NULL);
    memset(a, 255, size);
    for (k = 0; k < (kind == 0 ? 3 : 12); k++) {      /* blocks (kind 1: small ones, lines) */
      int c = 1 + rnd() % ncolors, x0 = rnd() % w, y0 = rnd() % h;
      int x1 = x0 + rnd() % (w / (kind == 1 ? 6 : 1) + 1), y1 = y0 + rnd() % (h / (kind == 1 ? 6 : 1) + 1);
      for (y = y0; y < h && y <= y1; y++)
        for (x = x0; x < w && x <= x1; x++)
          memcpy(a + (y * w + x) * 3, colors[c], 3);
    }
    if (kind == 2)                                      /* noise */
      for (k = 0; k < w * h / 3; k++)
        memcpy(a + (rnd() % (w * h)) * 3, colors[rnd() % (ncolors + 1)], 3);
    memcpy(b, a, size);
    {
      at_bitmap A = { w, h, a, 3 }, B = { w, h, b, 3 };
      thin_image_reference(&A, &bg, &e1);
      cancel_after = -1;
      thin_image(&B, &bg, &e2, test_cancel, NULL);
    }
    if (memcmp(a, b, size)) {
      if (bad++ < 5)
        printf("different: trial %d, %d x %d, kind %d\n", t, w, h, kind);
    }
    free(a);
    free(b);
  }
  printf("%d pictures, %d different\n", trials, bad);
  {
    /* a 600 x 600 block needs 300 passes; cancelled after 3, it stops at the 4th check */
    int w = 600, h = 600;
    unsigned char *a = calloc((size_t)w * h, 3);
    at_bitmap A = { w, h, a, 3 };
    at_color bg = { 255, 255, 255 };
    at_exception_type e = at_exception_new(NULL, NULL);
    calls = 0;
    cancel_after = 3;
    thin_image(&A, &bg, &e, test_cancel, NULL);
    printf("cancelled: asked %d times\n", calls);
    free(a);
    if (calls != 4)
      bad++;
  }
  return bad != 0;
}
