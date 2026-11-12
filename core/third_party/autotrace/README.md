# Autotrace 0.40.0

As bundled with Inkscape (`src/3rdparty/autotrace` at Inkscape commit 70feba2), from
https://github.com/autotrace/autotrace. Changes for KanzonasSVG:

- Left out: the input and output modules (`input.c`, `output.c`, `filename.c`,
  `module.c`), which read and write files; KanzonasSVG hands Autotrace a bitmap in memory
  and reads the splines back. `no-modules.c` stands in for their set-up functions.
- `config.h`: no translations (NLS).
- `shim/glib.h`, `shim/glib-object.h`: the few GLib definitions the tracing code uses, so
  that it builds without GLib.

Copyright (C) 2000-2002 Martin Weber and the Autotrace authors. GNU GPL version 2 or later
(COPYING); some files GNU LGPL 2.1 or later, as their headers say (COPYING.LIB).
