# Autotrace 0.40.0

As bundled with Inkscape (`src/3rdparty/autotrace` at Inkscape commit 70feba2), from
https://github.com/autotrace/autotrace. Changes for KanzonasSVG:

- Left out: the input and output modules (`input.c`, `output.c`, `filename.c`,
  `module.c`), which read and write files; KanzonasSVG hands Autotrace a bitmap in memory
  and reads the splines back. `no-modules.c` stands in for their set-up functions.
- `config.h`: no translations (NLS).
- `shim/glib.h`, `shim/glib-object.h`: the few GLib definitions the tracing code uses, so
  that it builds without GLib.
- `xstd.h` (`XGROW`, `XCAPACITY`), and its use in `curve.c`, `fit.c`, `pxl-outline.c` and
  `spline.c`: lists grown one element at a time are reallocated when their length reaches a
  power of two, to twice that, instead of at every element (building a list took time
  proportional to the square of its length: 147 s for a noisy picture in 256 colors under
  AddressSanitizer, 2.5 s now). The output is the same.
- `thin-image.c` (centerline thinning): looks only at the pixels that can be deleted (pixels
  of the color next to another one, kept in a list) instead of going over the whole picture
  on every pass, a solid area needing a pass for each pixel from its edge to its middle
  (20 s for a scanned page at 3 times its size, half an hour and more for big solid areas;
  a second or two now). The same pixels: `tests/thin_exact.c` checks it against the original
  (`tests/thin_reference.c`). It also stops when `test_cancel` says so (checked every pass;
  `thin_image` takes it, and `autotrace.c` passes it on and checks it after thinning), and the
  background color is passed along instead of kept in a static variable.
- `pxl-outline.c`: `find_centerline_pixels` checks `test_cancel` at each row (it only did after
  the whole picture).
- Fixes from Autotrace's own releases (checked up to 0.31.12) to the code carried here:
  `find_centerline_pixels` counts rows and columns in `unsigned int` (169cdf3; a `signed short`
  went negative past 32,767 and read far outside the picture: a crash on Centerline);
  `find_one_outline`'s outline and `fit_one_spline`'s spline start zeroed (356e4e8, eb2f6ae);
  `at_bitmap_copy` and `at_bitmap_init` multiply the size in `size_t` (ba1f172, c23e19d).
  The rest of 0.31.12's security fixes (GHSA-f57q-wgfx-9vp3, GHSA-4cx5-xpv3-hqq5) are in the
  file readers, left out here; the size they check (at most 65,535 pixels wide and high, what
  `at_bitmap` holds) KanzonasSVG's engine checks before calling Autotrace. Not brought over,
  as nothing here runs them: the fixes to despeckling (e55e676) and to Autotrace's own color
  reduction (90a7ff7), and the bound on subdividing curves (ce590cd; it recursed for ever with
  an error threshold of 0, and the engine keeps it at 0.1 or more).

Copyright (C) 2000-2002 Martin Weber and the Autotrace authors. GNU GPL version 2 or later
(COPYING); some files GNU LGPL 2.1 or later, as their headers say (COPYING.LIB).
