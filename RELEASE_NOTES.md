# Release notes

Short, plain-language notes for each version; the release text on GitHub is made from them.

## 1.0.1

New:
- A new icon, matching KanzonasPDF and KanzonasCAD: the cactus and sunflower with an orange
  "SVG" tag.
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
