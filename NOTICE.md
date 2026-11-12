# Notices

KanzonasSVG is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either
version 2 of the License, or (at your option) any later version (see LICENSE). It comes
with no warranty.

It is built on:

| Part | Where | Authors | License |
|---|---|---|---|
| Trace Bitmap's quantizer, filters and Potrace/Autotrace glue | `core/src` (from Inkscape's `src/trace`, changed) | Bob Jamison, Stéphane Gimenez, Marc Jeanmougin and other Inkscape authors; changes by Keith Lyding | GPL-2.0-or-later |
| Potrace 1.16 (the library part) | `core/third_party/potrace` | Peter Selinger | GPL-2.0-or-later |
| Autotrace 0.40 (as bundled with Inkscape, without its input/output modules and GLib) | `core/third_party/autotrace` | Martin Weber and other Autotrace authors | GPL-2.0-or-later (some files LGPL-2.1-or-later) |
| Qt for Python (PySide6) and Qt | the window, reading pictures, drawing SVGs | The Qt Company and contributors | LGPL-3.0 |
| Python | | Python Software Foundation | PSF License |

Complete source code: https://github.com/keithlyding/KanzonasSVG
Inkscape: https://gitlab.com/inkscape/inkscape. Potrace: https://potrace.sourceforge.net.
Autotrace: https://github.com/autotrace/autotrace.
