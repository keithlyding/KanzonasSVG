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

Copyright (C) 2000-2002 Martin Weber and the Autotrace authors. GNU GPL version 2 or later
(COPYING); some files GNU LGPL 2.1 or later, as their headers say (COPYING.LIB).
