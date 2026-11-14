# Release notes

Short, plain-language notes for each version; the release text on GitHub is made from them.

## 1.2

New:
- Edit the colors before tracing: the **Colors** box shows a swatch for each color the SVG
  is traced with. Select colors (or click the picture), then **Change color...**, **Merge**
  several shades into one for a simpler SVG, or **Leave out** a color so the SVG is see-through
  there. The picture itself never changes, and the edits still apply when you change the
  number of colors or crop.
- On the command line: `--list-colors`, `--recolor FROM=TO` and `--leave-out COLOR`.

## 1.1.1

New:
- Crop: *Trace > Crop picture* (Ctrl+R), then drag across the part of the picture to trace,
  for example the drawing in a screenshot without the program's toolbars around it. Auto
  settings picks the settings for that part. *Trace > Remove crop* (Ctrl+Shift+R) brings the
  whole picture back. On the command line: `--crop X,Y,W,H`.

Fixed:
- Background: Remove on a picture with transparent parts at its edge removes those parts, not
  a shape that covers most of the edge.
- Drawings, plans and screenshots of them trace much better with Auto settings: thin lines
  are kept (gray outlines used to disappear), in their own colors, and the picture is enlarged
  4 times first so lines a pixel wide trace cleanly.
- Auto settings now sets every setting, including Speckles, Smooth corners, Optimize,
  Tolerance and Enlarge first.
- Auto settings gives flat pictures with more than 16 colors (illustrations, maps, charts)
  all their colors, up to 64. Before, it stopped at 16 and treated them like a photo, so
  some colors were lost or swapped. Photos and paintings are handled as before.

## 1.1

New:
- KanzonasSVG updates itself. Once a day it checks GitHub for a newer version and says so in the
  status bar, with what's new since your version; **Update now** downloads it, checks it
  against the checksum published with the release, installs it and starts KanzonasSVG again
  (installed with the setup, unzipped, or the Linux AppImage). Your settings are kept.
- *Help > Check for updates...* checks at once; *Help > Check for updates automatically*
  turns the daily check off or on. Nothing is downloaded or installed until you click
  Update now.

Faster:
- Autotrace on very detailed pictures in many colors (a quarter faster on a noisy photo in
  256 colors).

This version is the first one that updates itself: from 1.0.x, install it by hand once.

## 1.0.4

This release brings together 1.0.2 and 1.0.3 (1.0.2 wasn't published on its own).

Faster:
- The window never freezes: SVGs are drawn by KanzonasSVG itself, 8 to 20 times faster, in the
  background, and pictures are opened in the background.
- Tracing uses all the computer's cores (a 12-megapixel photo: 1.9 s, now 1.0 s).
- Big pictures show a quick preview of the SVG within moments, then the full one.
- Changing the number of colors, Auto settings, and settings that don't change the colors
  (speckles, corners, background) are two to three times faster.

Fixed (found by a new battery of tests that tries to break it):
- On Windows, detailed pictures (photos, paintings) were traced with worse colors than on Linux.
- Quitting right after Copy SVG could crash the program.
- An SVG of thousands of small shapes could show only in part.
- With Smooth on, a clean picture could get near-copies of its colors as extra layers.
- Enlarge first on a big picture could use gigabytes of memory; very noisy pictures with very
  many colors could make SVGs of gigabytes. Both now have limits.
- A threshold of "nan" on the command line, and Auto settings keeping the threshold shown.

## 1.0.3

Faster:
- Big pictures show a quick preview of the SVG within moments, then the full one: a
  12-megapixel photo shows its first SVG in about a second instead of three.
- Changing the number of colors is about twice as fast, and Auto settings too.

## 1.0.2

Faster:
- The window never freezes: zooming, moving and new results used to freeze it for up to a
  second on photos. SVGs are now drawn by KanzonasSVG itself, 8 to 20 times faster, in the
  background, and pictures are opened in the background.
- Tracing uses all the computer's cores (a 12-megapixel photo: 1.9 s, now 1.0 s), and changing
  a setting that doesn't change the colors (speckles, corners, optimize, background) traces again
  about three times faster.

Fixed (found by a new battery of tests that tries to break it):
- On Windows, detailed pictures (photos, paintings) were traced with worse colors than on Linux
  (an overflow in the color reduction, from Inkscape's code). They now trace the same on both.
- Quitting right after Copy SVG could crash the program.
- An SVG of thousands of small shapes could show only in part in the window (and in some other
  programs). Very long paths are now split, and the window always shows the whole SVG.
- On a clean picture with Smooth on and many colors, near-copies of the picture's colors could
  come out as extra layers.
- Enlarge first on a big picture could use gigabytes of memory; pictures are now enlarged to at
  most 40 megapixels.
- A very noisy picture with very many colors could make an SVG of gigabytes; tracing now stops
  past 500 MB and says to use fewer colors, Smooth or Speckles.
- A threshold of "nan" on the command line, and Auto settings keeping the threshold shown.

## 1.0.1

New:
- A new icon and logo, matching KanzonasPDF and KanzonasCAD: the cactus and sunflower with an
  orange "SVG" (the logo is in Help > About KanzonasSVG).
- A Windows installer: download the setup file and run it (no administrator rights needed). It
  adds KanzonasSVG to the Start menu and to "Open with" for pictures, and installing a newer
  version over it updates it. The zip is still there if you'd rather not install.

## 1.0

New:
- Turn pictures into SVG files: open, drag or paste a picture and see the SVG beside it, then
  save it or copy it into another program.
- Auto settings: each picture gets the settings that suit it (exactly a logo's colors,
  smoothing for JPEGs and scans, transparent backgrounds kept, black and white for scans of
  dark lines). Change anything after.
- Remove a solid background, white or any color: around the picture only (that color inside
  the logo stays), or everywhere.
- Every mode of Inkscape's Trace Bitmap: colors, grays, brightness steps, black and white,
  edges, Autotrace colors and centerline.
- Exact colors and sharp edges, holes that stay holes, and faster on big pictures than
  Inkscape's own Trace Bitmap.
- Small pictures are traced at twice their size for smoother curves.
- A command line for many pictures at once (`kanzonassvg-cli.exe --help`).
