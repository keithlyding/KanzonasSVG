# Release notes

Short, plain-language notes for each version; the release text on GitHub is made from them.

## 1.0.2

Faster:
- The window never freezes: zooming, moving and new results used to freeze it for up to a
  second on photos. SVGs are now drawn by KanzonasSVG itself, 8 to 20 times faster, in the
  background, and pictures are opened in the background.
- Tracing uses all the computer's cores (a 12-megapixel photo: 1.9 s, now 1.0 s), and changing
  a setting that doesn't change the colors (speckles, corners, optimize, background) traces again
  about three times faster.

Fixed (found by a new battery of tests that tries to break it):
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
