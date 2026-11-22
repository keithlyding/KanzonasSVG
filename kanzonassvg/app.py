"""The KanzonasSVG window: open a picture, pick settings, see the SVG beside it, save it."""

import itertools
import os
import sys
import threading
from dataclasses import replace

from PySide6.QtCore import QUrl, QByteArray, QEvent, QMimeData, QObject, QPointF, QRect, QRectF, QSettings, QSize, Qt, \
    QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, \
    QPalette, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, \
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar, \
    QMenu, QProgressDialog, QPushButton, QScrollArea, QSpinBox, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from kanzonassvg import APP_NAME, __version__, engine, export, i18n, image, tracing
from kanzonassvg.colors_panel import ColorsPanel
from kanzonassvg.i18n import tr

# (label, engine mode)
MODES = [
    ("Colors", engine.COLORS),
    ("Grays", engine.GRAYS),
    ("Brightness steps", engine.BRIGHTNESS_STEPS),
    ("Black and white", engine.BRIGHTNESS),
    ("Edges", engine.EDGES),
    ("Autotrace: colors", engine.AUTOTRACE),
    ("Autotrace: centerline", engine.CENTERLINE),
]
POTRACE_MODES = {engine.COLORS, engine.GRAYS, engine.BRIGHTNESS_STEPS, engine.BRIGHTNESS, engine.EDGES}
MULTI_MODES = {engine.COLORS, engine.GRAYS, engine.BRIGHTNESS_STEPS}
AUTOTRACE_MODES = {engine.AUTOTRACE, engine.CENTERLINE}

def help_html():
    """The help in the language in use."""
    if i18n.language() == "es":
        from kanzonassvg.help_es import HELP_HTML_ES
        return HELP_HTML_ES
    return HELP_HTML


def picture_filter():
    """The file dialog's types (in the user's language)."""
    return tr("Pictures") + " (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.ico);;" + tr("All files") + " (*)"

HELP_HTML = """
<h2>KanzonasSVG</h2>
<p>KanzonasSVG turns a picture (a logo, a drawing, a scan) into an SVG file: shapes
instead of pixels, sharp at any size. Edit the SVG afterwards in Inkscape, Illustrator
or another vector editor.</p>
<p>This help is in chapters: click one in the list to go to it. Type in the box at the top
(Ctrl+F) to search: every match is marked, the chapters that have them show how many, and
Enter (or F3) goes to the next one, Shift+Enter to the one before. The help can stay open
while you work.</p>
<p>The commands are on the <b>ribbon</b> at the top of the window, in three tabs: <b>Home</b>
(opening, saving, Undo, Auto settings and the tools), <b>Picture</b> (the tools, the color
edits, the crop and the eraser) and <b>View</b> (zoom, what's shown, help). The same commands
are in the menus, by the same names (the ribbon's are sometimes shorter), with their shortcuts.
Hover over a button to see what it does. Double-click a tab, or use <i>View &gt; Collapse the
ribbon</i> (Ctrl+F1), to show only the tabs' names; click a tab to open it again.</p>
<h3>Making an SVG</h3>
<ol>
<li><b>Open a picture</b>: <i>File &gt; Open picture...</i> (Ctrl+O), drag a file into the
window, or copy a picture and use <i>File &gt; Paste picture</i> (Ctrl+V).
<i>File &gt; Open recent</i> lists the last 10 pictures opened (<i>Clear the list</i> empties
it).</li>
<li><b>Check the settings</b> on the right. When you open a picture, KanzonasSVG picks the
settings that suit it (see <b>Auto settings</b> below) and traces it. Change any setting and
the SVG on the right side of the window updates (unless <i>Trace &gt; Update automatically</i>
is off: then press <i>Trace &gt; Update now</i>, F5).</li>
<li><b>Save</b>: <i>File &gt; Save as SVG...</i> (Ctrl+Shift+S), <i>File &gt; Save as PDF...</i>,
<i>File &gt; Save as EPS...</i> or <i>File &gt; Save as DXF...</i> (on the ribbon, <b>Save as</b> and
its arrow; see <b>Saving</b> below), or <i>File &gt; Copy SVG</i> (Ctrl+Shift+C) to paste it
straight into Inkscape or another program.</li>
</ol>
<h3>The tools</h3>
<p>What a click or a drag on the picture does depends on the tool that's on: one of three, on
the ribbon (<b>Tools</b>, on the Home and Picture tabs) and in the Trace menu. The bar above
the picture and the SVG says what the tool that's on does, and has its controls. Esc goes back
to Select colors.</p>
<ul>
<li><i>Trace &gt; Select colors</i> (on at first): a click on the picture or the SVG selects the
color traced there, Ctrl+click selects more, and a drag moves the picture. The selected colors
are marked on the SVG (everything else faded) and the bar has <b>Change color</b>,
<b>Merge</b> and <b>Leave out</b> for them (see <b>Editing colors</b>). With the mouse over the
picture, the status bar says which color a click there selects. Right-click for the color
commands.</li>
<li><i>Trace &gt; Crop picture</i> (Ctrl+R): drag across the part of the picture to trace (see
<b>Cropping</b>). <b>Cancel</b> on the bar, or Esc, stops it.</li>
<li><i>Trace &gt; Erase on the picture</i> (Ctrl+E): drag on the picture to wipe out what
shouldn't be traced; a circle shows the eraser and its size (see <b>Erasing parts of the
picture</b>). The bar has a <b>Size</b> slider, <b>Restore the picture</b> and <b>Done</b>.</li>
</ul>
<h3>Auto settings</h3>
<p>The <b>Auto settings</b> button (or <i>Trace &gt; Auto settings</i>, Ctrl+Shift+A) picks the
settings for the picture: how many colors it needs (the fewest after which more colors no
longer make it visibly closer: a logo or a flat illustration gets exactly its colors, up to 64,
a photo or painting a number up to 16 that keeps the file reasonable), <b>Smooth</b> when it has JPEG blotches or scan noise,
<b>Background: Remove</b> when its background is transparent (so the SVG's is too), and
<b>Black and white</b> with its <b>Threshold</b> for a scan of dark lines on a light page.
For <b>line art</b> (a plan, a drawing or a screenshot of one: thin lines on a plain
background) it keeps the lines' own colors, leaves <b>Smooth</b> off (it would wipe thin lines
out) and sets <b>Enlarge first</b> to 4 times, so lines a pixel or two wide trace as solid
shapes. It also puts the curve settings (<b>Speckles</b>, <b>Smooth corners</b>,
<b>Optimize</b>, <b>Tolerance</b>) back to the values that suit the picture: Auto sets every
setting but <b>Snap shapes</b>, which stays as you set it. The status bar says what it picked. Change anything after: Auto doesn't change it
back.</p>
<p><i>Trace &gt; Auto settings for new pictures</i> (on at first) does this for every picture you
open or paste; turn it off to keep your own settings for each new picture.</p>
<h3>Modes</h3>
<ul>
<li><b>Colors</b>: the picture in a few flat colors, one layer per color. Best for logos.
<b>Colors</b> sets how many (count the background too: a red logo on white is 2).</li>
<li><b>Grays</b>: the same in shades of gray.</li>
<li><b>Brightness steps</b>: layers of gray by brightness, from dark to light.</li>
<li><b>Black and white</b>: one black shape for everything darker than <b>Threshold</b>.</li>
<li><b>Edges</b>: the outlines of shapes, found by edge detection.</li>
<li><b>Autotrace: colors</b>: colors traced with Autotrace instead of Potrace: fewer,
looser curves.</li>
<li><b>Autotrace: centerline</b>: lines along the middle of strokes (handwriting, line art)
instead of outlines.</li>
</ul>
<h3>Settings</h3>
<ul>
<li><b>Smooth</b>: evens out noise, JPEG blotches and texture before the colors are picked,
while keeping edges sharp.</li>
<li><b>Stack</b>: each color layer also covers the area of the layers above it, so no gaps
show between colors. Off: the layers are tiled side by side.</li>
<li><b>Background</b>: <i>Keep</i> traces the background like any color. <i>Remove</i> leaves
out the picture's background (its transparent part when its edge has one, otherwise the color
that most of its edge has, light or dark) around the
picture: the SVG is see-through there, and that color inside shapes (the white inside a
logo's letters) stays. <i>Remove, also inside</i> leaves that color out everywhere, so gaps
inside shapes are see-through too. (Brightness steps: the bottom layer is left out. Autotrace
always leaves out white, or with Remove, the background color, everywhere.)</li>
<li><b>Invert</b>: traces the light parts instead of the dark ones.</li>
<li><b>Speckles</b>: drops spots of up to this many pixels.</li>
<li><b>Smooth corners</b>: 0 keeps every corner sharp; higher rounds them off.</li>
<li><b>Optimize</b>: joins curve segments (smaller files); <b>Tolerance</b> is how far that may
move the curve.</li>
<li><b>Snap shapes</b> (off at first): edges that are all but straight become straight lines,
lines within 1.5 degrees of level or upright become exactly level or upright, and round shapes
within half a pixel of a circle or an ellipse (with level axes) become perfect ones. For
cutting machines, lasers, CAD and clean logos: fewer nodes, square corners stay square. It can
move an edge by up to half a pixel, and evens out art that was a little uneven on purpose, so
it's yours to turn on (Auto leaves it as it is). Not in the Autotrace modes.</li>
<li><b>Error threshold</b> and <b>Filter passes</b> (Autotrace): how closely curves follow
the outline, and how much outlines are smoothed first.</li>
<li><b>Keep line widths</b> (centerline): gives each line its width in the picture.</li>
<li><b>Enlarge first</b>: traces the picture at 2 or 4 times its size, for smoother curves on
small pictures. <i>Auto</i> does 2 times for pictures under 1000 pixels. The SVG keeps the
picture's size either way. A picture is never enlarged past 40 megapixels (a big picture gains
nothing from it); the status bar says how much it was.</li>
</ul>
<p>The settings are kept for next time. <i>Trace &gt; Reset settings</i> (or the
<b>Reset settings</b> button) puts them all back to how they started.</p>
<p>A big picture (over 3 megapixels) first shows a quick preview, traced from a smaller copy,
while the whole picture is traced; the status bar says so, and <i>Save</i> and <i>Copy SVG</i>
wait for the whole picture's SVG.</p>
<h3>Editing colors</h3>
<p>In <b>Colors</b>, <b>Grays</b> and <b>Autotrace: colors</b>, the <b>Colors</b> box shows the
colors the SVG is traced with, one swatch each. Click a swatch to select its color, and
Ctrl+click more to select them too (Ctrl+click a selected one to unselect it). Clicking the
picture or the SVG does the same with the color traced there (with the <b>Select colors</b>
tool on): the status bar says which color a click selects before you click. The selected
colors are marked on the SVG: everything else is faded until you select none
(<i>Colors &gt; Select no color</i>, or Esc). Then use the buttons in the Colors box, on the bar
above the picture, on the ribbon's Picture tab, in the Colors menu, or right-click a swatch,
the picture or the SVG:</p>
<ul>
<li><b>Change color...</b> (<i>Colors &gt; Change color...</i>) traces them as another color you
pick: the shapes stay, only their color changes.</li>
<li><b>Merge</b> (<i>Colors &gt; Merge colors...</i>) traces two or more selected colors as one
color, in one layer: pick which of them from the list it opens (biggest first), or
<b>Another color...</b>. For a picture with too many shades of the same color, merge the
shades you don't need apart. Merged colors show as one swatch.</li>
<li><b>Leave out</b> (<i>Colors &gt; Leave out</i>, Delete) leaves them out: the SVG is
see-through there (a crossed-out swatch; select it and use <b>Put back</b> to trace it again,
in its own color; <i>Edit &gt; Undo</i> brings back a color it had before).</li>
<li><b>Reset colors</b> (<i>Colors &gt; Reset colors</i>) undoes the edits of the selected
colors, or of all when none is selected.</li>
</ul>
<p>The <b>background</b> (the color around the picture, or its transparent part: what
<b>Background: Remove</b> leaves out) has a swatch of its own, with a dashed frame, even when
the same color is also inside the picture (the white inside a letter): editing one leaves the
other as it is. Clicking the background selects its swatch, clicking that color inside the
picture the other. (The command line's <code>--recolor</code> and <code>--leave-out</code> change
a color everywhere, the background too.)</p>
<p>The picture itself never changes, and the edits are for the picture shown: a new picture
starts without them, and <i>Reset settings</i> clears them. They still apply when the colors
are picked again (another number of colors, Smooth, a crop, Auto settings): each edit goes to
the color nearest the one it was made on (within 24 levels). An edit no color matches any more
is kept, and the box says so; it applies again if that color comes back. The status bar says
how many colors are edited. On the command line: <code>--list-colors</code>,
<code>--recolor FROM=TO</code> and <code>--leave-out COLOR</code>.</p>
<h3>Undo</h3>
<p><i>Edit &gt; Undo</i> (Ctrl+Z) goes back to the SVG before, as it was traced: its settings,
color edits and crop. <i>Edit &gt; Redo</i> (Ctrl+Y, or Ctrl+Shift+Z) goes forward again. Every
SVG traced for the picture shown can be gone back to; a change made after an Undo drops what
Redo would have brought back, and a new picture starts afresh.</p>
<h3>Cropping</h3>
<p>To trace only part of a picture (the drawing in a screenshot, without the program's
toolbars around it; one logo of several), use <i>Trace &gt; Crop picture</i> (Ctrl+R, or
<b>Crop</b> on the ribbon) and drag across that part on the left side. Only it is shown and traced, and the SVG is its size;
with <i>Auto settings for new pictures</i> on, Auto picks the settings for the part (a
screenshot's toolbars can make a drawing look like something else to it). Crop again to
crop further; Esc or <b>Cancel</b> on the bar stops cropping before you drag. <i>Trace &gt; Remove crop</i>
(Ctrl+Shift+R) brings the whole picture back. The command line's <code>--crop X,Y,W,H</code>
does the same.</p>
<h3>Saving</h3>
<p>Pick the kind of file with its command: <i>File &gt; Save as SVG...</i> (Ctrl+Shift+S),
<i>File &gt; Save as PDF...</i>, <i>File &gt; Save as EPS...</i> or <i>File &gt; Save as DXF...</i>
(on the ribbon, <b>Save as</b> saves the kind its face shows, and its arrow lists all four:
the face then shows the one used last). Each asks where, with the name's extension filled in.
<i>File &gt; Save...</i> (Ctrl+S) asks the first time (as the kind saved last), then saves to
the same file again.</p>
<ul>
<li><b>SVG</b>: for vector editors (Inkscape, Illustrator, Affinity), cutting machines (Cricut
Design Space, Silhouette Studio) and web pages.</li>
<li><b>PDF</b> and <b>EPS</b>: one page the size of the picture, in its colors, for printers,
sign makers, Illustrator and programs that don't read SVG.</li>
<li><b>DXF</b>: for CAD, laser, CNC and vinyl cutting programs (LightBurn, AutoCAD, LibreCAD,
Fusion): each shape's outlines as lines (curves become short straight pieces, within 0.025 mm
of them), one layer for each color. A DXF can't hold fill colors, only outlines, and doesn't
say its unit: it's in millimeters, or in inches when <b>Saved width</b> is in inches, so set
that unit when a program asks.</li>
</ul>
<p>Each color is a group of its own, named by its color (an Inkscape layer; in a DXF, a
layer such as COLOR_B2002D): programs that show groups list the colors instead of hundreds of
loose shapes. (In the Autotrace modes a color can come back above another, and gets a
second group, so the shapes stay in their order.)</p>
<p><b>Saved width</b> (under <b>Size</b>) sets how big the file is: <i>Picture's pixels</i>
keeps the picture's own size, 96 pixels to the inch (as browsers, Inkscape and Illustrator
count them), or give a width in <i>Inches</i> or <i>Millimeters</i> and the height follows.
The line under it shows the size the files get. It changes only what's saved (and copied),
not the trace, and is kept for next time.</p>
<h3>Erasing parts of the picture</h3>
<p>To leave something out of the trace (a watermark, a smudge, text next to a logo, a stray
mark), use <i>Trace &gt; Erase on the picture</i> (Ctrl+E) and drag across it on the left
side (or use <b>Erase</b> on the ribbon). A circle under the mouse shows the eraser, as big as
what it wipes out. What you drag over becomes see-through, as a transparent picture's
background is, and the SVG updates when you let go. (With <b>Background: Remove</b> it's left
out; with <b>Keep</b>, a see-through part is traced as white.) The <b>Size</b> slider on the bar
above the picture, <i>Trace &gt; Smaller eraser</i> ([) and <i>Trace &gt; Bigger eraser</i> (])
change its size; the middle mouse button still moves the picture. <b>Done</b> on the bar,
Ctrl+E again or Esc stops erasing. <i>Edit &gt; Undo</i> takes strokes back one by one,
and <i>Trace &gt; Restore the picture</i> (Ctrl+Shift+E) brings back everything erased. The
picture file itself never changes; a new picture starts with nothing erased. Erasing works
with a crop too (it's kept when you crop or remove the crop).</p>
<h3>Many pictures at once</h3>
<p><i>File &gt; Convert many pictures...</i> (Ctrl+Shift+O) traces and saves a list of pictures
in one go. It also opens when you pick several pictures in <i>Open picture</i>, or drag several
pictures (or a folder) into the window. Add pictures with <b>Add pictures...</b>, <b>Add a
folder...</b> (the pictures in it, not SVGs) or by dragging them into the list, then choose:</p>
<ul>
<li><b>Settings</b>: <i>Auto settings for each picture</i> (each gets the settings that suit it,
as when you open it, with <b>Snap shapes</b> as you set it), or <i>The settings shown now</i>, the same for all (not the color edits,
which are for the picture shown, nor its crop).</li>
<li><b>Save as</b>: SVG, PDF, EPS or DXF, at the <b>Saved width</b> set under Size (every picture
that wide, or each at its own size in pixels).</li>
<li><b>Save to</b>: next to each picture, with its name, or in one folder. Files already there
are skipped unless <b>Replace files that are already there</b> is on.</li>
</ul>
<p><b>Convert</b> starts; the list says what happened to each picture (saved, with its shapes
and nodes; skipped; or why it failed, and the next one is done anyway). <b>Stop</b> stops at once
(the picture being traced isn't saved, and the rest aren't done). <b>Open the folder</b> shows the files. The window
stays usable while it works. The command line does the same for scripts.</p>
<h3>Looking at it</h3>
<p>Above the SVG: its size, as Save writes an SVG, how many shapes it has, and how many
<b>nodes</b> (the points its outlines go through; a cutting machine turns at each, and fewer
cut cleaner: raise <b>Tolerance</b>, <b>Smooth corners</b> or <b>Speckles</b>, or use fewer
colors, for fewer). The status bar says the same.</p>
<p>The left side shows the picture; <i>View &gt; Show colors to trace</i> (Ctrl+T) shows it
with its colors reduced, as it will be traced. <i>View &gt; Show outlines</i> (Ctrl+L) shows
the SVG as its outlines, thin dark lines, with its nodes as small blue squares (when zoomed
to 150% or more, or when there are no more than 3,000 of them): to see where a cutting
machine will go, and what Snap shapes, Tolerance and Speckles change. Both sides zoom and move
together: the mouse wheel moves the picture up and down (Shift+wheel: sideways), Ctrl+wheel
zooms, and a drag moves it. <i>View &gt; Zoom to fit</i> (Ctrl+0), <i>View &gt; Actual size</i>
(Ctrl+1), <i>View &gt; Zoom in</i> (Ctrl++), <i>View &gt; Zoom out</i> (Ctrl+-).</p>
<p>The wheel scrolls the settings panel even over a number or a list in it: those change with
the wheel only once you've clicked into them.</p>
<h3>Keyboard shortcuts</h3>
<table cellpadding="2">
<tr><td>Ctrl+O</td><td>Open picture</td></tr>
<tr><td>Ctrl+Shift+O</td><td>Convert many pictures</td></tr>
<tr><td>Ctrl+V</td><td>Paste picture</td></tr>
<tr><td>Ctrl+S</td><td>Save</td></tr>
<tr><td>Ctrl+Shift+S</td><td>Save as SVG</td></tr>
<tr><td>Ctrl+Shift+C</td><td>Copy SVG</td></tr>
<tr><td>F5</td><td>Update now</td></tr>
<tr><td>Ctrl+Shift+A</td><td>Auto settings</td></tr>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>Undo / Redo</td></tr>
<tr><td>Ctrl+click</td><td>Select more colors (a swatch, the picture or the SVG)</td></tr>
<tr><td>Delete</td><td>Leave out (the selected colors)</td></tr>
<tr><td>Esc</td><td>Back to Select colors; then select no color</td></tr>
<tr><td>Ctrl+R / Ctrl+Shift+R</td><td>Crop picture / Remove crop</td></tr>
<tr><td>Ctrl+T</td><td>Show colors to trace</td></tr>
<tr><td>Ctrl+L</td><td>Show outlines</td></tr>
<tr><td>Ctrl+E / Ctrl+Shift+E</td><td>Erase on the picture / Restore the picture</td></tr>
<tr><td>[ / ]</td><td>Smaller eraser / Bigger eraser</td></tr>
<tr><td>Ctrl+0 / Ctrl+1</td><td>Zoom to fit / Actual size</td></tr>
<tr><td>Ctrl++ / Ctrl+-</td><td>Zoom in / Zoom out</td></tr>
<tr><td>Ctrl+wheel / wheel</td><td>Zoom / move the picture (Shift+wheel: sideways)</td></tr>
<tr><td>Ctrl+F1</td><td>Collapse the ribbon</td></tr>
<tr><td>F1</td><td>How to use KanzonasSVG</td></tr>
<tr><td>Ctrl+Q</td><td>Quit</td></tr>
</table>
<h3>Command line</h3>
<p>The same tracing works from a command prompt, for many files at once (on Windows,
<code>kanzonassvg-cli.exe</code> in the program's folder). Run it with <code>--help</code> to
see every option, for example:<br>
<code>kanzonassvg-cli --colors 4 *.png -o svgs</code><br>
<code>kanzonassvg-cli logo.png -o logo.dxf --width 100mm</code> (the extension picks the type;
<code>--format pdf</code> for many files; <code>--width</code> in <code>in</code> or <code>mm</code>)</p>
<h3>Language</h3>
<p><i>View &gt; Language</i>: <i>Automatic (the system's)</i>, <i>English</i> or
<i>Español</i>. KanzonasSVG switches the next time it starts (its menus, settings, messages, this
help, and Qt's own buttons and dialogs). The command line is always in English.</p>
<h3>Updates</h3>
<p>Once a day, a few seconds after it starts, KanzonasSVG asks GitHub whether a newer version is
out (<i>Help &gt; Check for updates automatically</i>, on at first; it sends nothing about you
or your pictures, and when you're offline it just tries again the next day). When there is one,
a notice in the status bar says so: <b>What's new</b> shows what changed since your version,
<b>Update now</b> updates it, <b>Download</b> opens the release page, <b>Skip this version</b>
stops telling you about that version, and <b>Later</b> hides the notice.
<i>Help &gt; Check for updates...</i> asks at once.</p>
<p><b>Update now</b> downloads the new version, checks it against the checksum GitHub
publishes with the release (nothing is installed if they differ), closes KanzonasSVG, puts
the new version in place and starts it again. Installed with the setup, it runs the new setup
over this one; unzipped from KanzonasSVG-windows.zip, it replaces the program files in that
folder; the Linux AppImage replaces its file. Your settings are kept. (Run from its source code,
KanzonasSVG only tells you.) Nothing is ever downloaded or installed until you click
<b>Update now</b>.</p>
<h3>About</h3>
<p><i>Help &gt; About KanzonasSVG</i> shows the version, where the tracing comes from, and the
license.</p>
"""


class View(QObject):
    """Zoom and position, shared by both sides so they move together."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.scale = 1.0  # screen pixels per picture pixel
        self.cx = 0.0  # picture point at the middle of the view
        self.cy = 0.0
        self.width = 0  # picture size
        self.height = 0
        self.fitted = True

    def set_picture(self, w, h):
        self.width, self.height = w, h
        self.cx, self.cy = w / 2, h / 2

    def fit(self, size):
        if not self.width or size.width() < 2 or size.height() < 2:
            return
        self.scale = min(size.width() / self.width, size.height() / self.height) * 0.95
        self.cx, self.cy = self.width / 2, self.height / 2
        self.fitted = True
        self.changed.emit()

    def zoom(self, factor, anchor=None, size=None):
        new = max(0.01, min(64.0, self.scale * factor))
        if anchor is not None and size is not None:
            # keep the picture point under the cursor where it is
            px = self.cx + (anchor.x() - size.width() / 2) / self.scale
            py = self.cy + (anchor.y() - size.height() / 2) / self.scale
            self.cx = px - (anchor.x() - size.width() / 2) / new
            self.cy = py - (anchor.y() - size.height() / 2) / new
        self.scale = new
        self.fitted = False
        self.changed.emit()

    def move(self, dx, dy):
        self.cx -= dx / self.scale
        self.cy -= dy / self.scale
        self.fitted = False
        self.changed.emit()

    def target(self, size):
        """Where the whole picture goes in a widget of <size>."""
        x = size.width() / 2 - self.cx * self.scale
        y = size.height() / 2 - self.cy * self.scale
        return QRectF(x, y, self.width * self.scale, self.height * self.scale)


OURS = "application/x-kanzonassvg"
_clipboard_hooked = []


def _release_clipboard():
    """Before Qt shuts down, swap the SVG this app put on the clipboard for the same SVG as
    plain text: Qt destroys the clipboard's data after Python has stopped, and data made from
    Python (Copy SVG) then crashed the program on its way out (found by tests/battery_app.py;
    KanzonasPDF does the same, kanzonas/clip.py)."""
    try:
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is not None and md.hasFormat(OURS):
            cb.setText(md.text())
    except Exception:
        pass


def _hook_clipboard_release():
    if _clipboard_hooked:
        return
    import atexit

    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(_release_clipboard)
    atexit.register(_release_clipboard)
    _clipboard_hooked.append(True)


def svg_renderer(svg):
    """A renderer for an SVG that KanzonasSVG's engine just wrote. Qt stops reading a path at
    about 32,000 points unless it's told the SVG is trusted (it is: it's ours), and a picture of
    thousands of small shapes, or a shape with thousands of holes, showed only in part."""
    r = QSvgRenderer()
    if hasattr(r, "setOptions"):
        from PySide6.QtSvg import QtSvg

        r.setOptions(QtSvg.Option.AssumeTrustedSource)
    r.load(QByteArray(svg.encode("utf-8")))
    return r


class RenderThread(QThread):
    """Draws one side of the window in the background: the window never waits for a drawing
    (an SVG of a photo takes 0.3-0.4 s to draw, and the window used to freeze that long at every
    zoom and every new result). Only the latest request is drawn; older ones are skipped."""

    drawn = Signal(int, object, object)  # request number, QImage, the request's view key

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._request = None
        self._quit = False
        self._svg_id = None
        self._renderer = None
        self._mark_id = None
        self._marker = None     # the SVG with the selected colors marked (Canvas.set_mark), parsed once

    def request(self, number, kind, content_id, content, key, target, size, dpr):
        with self._lock:
            self._request = (number, kind, content_id, content, key, target, size, dpr)
            self._wake.notify()

    def stop(self):
        with self._lock:
            self._quit = True
            self._wake.notify()
        self.wait()

    def run(self):
        while True:
            with self._lock:
                while self._request is None and not self._quit:
                    self._wake.wait()
                if self._quit:
                    return
                req, self._request = self._request, None
            try:
                self.drawn.emit(req[0], self._draw(*req[1:]), req[4])
            except Exception:  # a drawing that fails leaves the old one shown, never a crash
                pass

    def _draw(self, kind, content_id, content, key, target, size, dpr):
        w, h = max(1, int(size.width() * dpr)), max(1, int(size.height() * dpr))
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if kind in ("svg", "outlines"):
            # drawn by the engine (through ctypes: Python's lock is let go, so the window keeps
            # going; Qt's SVG renderer held it all along, 0.3 s for a photo's SVG)
            svg, nodes, mark_id, mark = content
            if kind == "outlines":
                p.fillRect(target, Qt.GlobalColor.white)
            p.end()
            if self._svg_id != content_id:
                if self._renderer is not None:
                    self._renderer.close()
                self._renderer = engine.Drawing(svg)  # parsed once, used only in this thread
                self._svg_id = content_id
            box = (target.left() * dpr, target.top() * dpr, target.width() * dpr, target.height() * dpr)
            if mark is not None:
                # the selected colors marked: the SVG with the other colors faded (under the
                # outlines, when they're shown), made here, not on the window's thread (40 ms
                # for a photo's SVG)
                if self._mark_id != (content_id, mark_id):
                    if self._marker is not None:
                        self._marker.close()
                    self._marker = engine.Drawing(tracing.marked(svg, mark))
                    self._mark_id = (content_id, mark_id)
                self._marker.render_image(img, *box)
                if kind != "outlines":
                    return img
            if kind == "outlines":
                self._renderer.render_outlines_image(img, *box, nodes)
            else:
                self._renderer.render_image(img, *box)
            return img
        else:
            # only the part of the picture that shows, scaled (zoomed in on a 12-megapixel
            # picture, scaling all of it every time cost most of the drawing)
            visible = target.intersected(QRectF(0, 0, size.width(), size.height()))
            if not visible.isEmpty():
                sx = content.width() / target.width()
                sy = content.height() / target.height()
                src = QRectF((visible.left() - target.left()) * sx, (visible.top() - target.top()) * sy,
                             visible.width() * sx, visible.height() * sy)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, target.width() < content.width() * 2)
                p.drawImage(visible, content, src)
        p.end()
        return img


def colorbox(rgb):
    """A small square of that color, in a label's rich text."""
    return '<span style="background-color:#%02x%02x%02x">&nbsp;&nbsp;&nbsp;&nbsp;</span>' % tuple(rgb)


def erase(img, strokes):
    """A copy of img with the strokes (radius, points) made see-through."""
    out = img.copy()
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    for radius, pts in strokes:
        p.setPen(QPen(Qt.GlobalColor.black, 2 * radius, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        if len(pts) == 1:
            p.drawPoint(QPointF(*pts[0]))
        else:
            p.drawPolyline([QPointF(x, y) for x, y in pts])
    p.end()
    return out


def _checker_brush():
    tile = QImage(20, 20, QImage.Format.Format_RGB32)
    tile.fill(QColor(255, 255, 255))
    p = QPainter(tile)
    p.fillRect(0, 0, 10, 10, QColor(232, 232, 232))
    p.fillRect(10, 10, 10, 10, QColor(232, 232, 232))
    p.end()
    from PySide6.QtGui import QBrush
    return QBrush(tile)


class Canvas(QWidget):
    """One side: the picture, or the SVG. Drawn by its RenderThread; until the drawing for the
    current zoom and position is ready, the last one is shown moved and scaled to match."""

    _ids = itertools.count(1)
    cropped = Signal(QRectF)  # (Crop picture) the rectangle dragged, in picture pixels
    clicked = Signal(QPointF, bool)  # a click (no drag), in picture pixels, and whether Ctrl was held

    erased = Signal(float, list)  # (Erase on the picture) a stroke: its radius and points, in picture pixels
    hovered = Signal(object)  # the mouse over it (no button held), in picture pixels; None: it left
    menu_requested = Signal(QPointF, object)  # a right-click: in picture pixels, and where on the screen

    def __init__(self, view, title):
        super().__init__()
        self.crop_mode = False
        self.erase_mode = False
        self.eraser = 12  # the eraser's radius, in screen pixels
        self.stroke = None  # the points of the stroke being dragged, in widget coordinates
        self.band = None  # [start, end] of the rectangle being dragged, in widget coordinates
        self.view = view
        self.title = title
        self.picture = None  # QImage
        self.svg = None  # SVG text
        self.outlines = False  # View > Show outlines (the SVG side)
        self.nodes = 0  # the SVG's node count (for whether to show its nodes)
        self.content_id = 0
        self.message = ""
        self.cache = None  # (key, QImage, scale, cx, cy) of the last drawing
        self.drag = None
        self.number = 0  # of the latest drawing asked for
        self.checker = _checker_brush()
        self.mark = None  # (the SVG side) the selected colors ((r, g, b), ...): the others drawn faded
        self.mark_id = 0
        self.pointing = False  # clicks select colors here (the Select colors tool, with colors to select)
        self.mouse = None  # where the mouse is (for the eraser's circle)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        view.changed.connect(self.redraw)
        self.thread = RenderThread()
        self.thread.drawn.connect(self._drawn)
        self.thread.start()

    @property
    def renderer(self):
        """(For tests and old code: whether an SVG is shown.)"""
        return self.svg

    def stop(self):
        self.thread.stop()

    def has_content(self):
        return (self.picture is not None and not self.picture.isNull()) or bool(self.svg)

    def set_picture(self, img):
        self.picture, self.svg = img, None
        self.content_id = next(self._ids)
        self.redraw()

    def set_svg(self, svg):
        self.picture, self.svg = None, svg or None
        self.content_id = next(self._ids)
        if not svg:
            self.cache = None
        self.redraw()

    def set_message(self, text):
        self.message = text
        self.update()

    def set_mark(self, colors):
        """Mark these colors ((r, g, b), ...) on the SVG: the others faded. None: no mark."""
        colors = tuple(tuple(c) for c in colors) if colors else None
        if colors != self.mark:
            self.mark = colors
            self.mark_id += 1
            self.redraw()

    def set_pointing(self, on):
        """Clicks here select colors: the hand cursor shows it (while no other tool is on)."""
        self.pointing = on
        self._cursor()

    def _cursor(self):
        if self.erase_mode or self.crop_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.pointing and self.has_content():
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

    def set_outlines(self, on):
        """View > Show outlines: the SVG drawn as its outlines and nodes."""
        if on != self.outlines:
            self.outlines = on
            self.redraw()

    # nodes shown when they can be told apart: at 150% zoom or more, or when there are few
    NODES_ZOOM, NODES_FEW = 1.5, 3000

    def show_nodes(self):
        return self.view.scale >= self.NODES_ZOOM or self.nodes <= self.NODES_FEW

    def _key(self):
        return (self.content_id, self.view.scale, self.view.cx, self.view.cy, self.width(), self.height(),
                self.devicePixelRatioF(), bool(self.svg) and self.outlines, bool(self.svg) and self.show_nodes(),
                self.mark_id if self.svg and self.mark is not None else 0)

    def redraw(self):
        self.update()
        if not self.has_content() or not self.view.width:
            return
        self.number += 1
        mark = (self.mark_id, self.mark)
        if self.svg and self.outlines:
            kind, content = "outlines", (self.svg, self.show_nodes()) + mark
        else:
            kind, content = ("svg", (self.svg, False) + mark) if self.svg else ("picture", self.picture)
        self.thread.request(self.number, kind, self.content_id, content, self._key(),
                            self.view.target(self.size()), self.size(), self.devicePixelRatioF())

    def _drawn(self, number, img, key):
        if key[0] != self.content_id and self.cache is not None and self.cache[0][0] == self.content_id:
            return  # an older content's drawing, and the current one is already shown
        self.cache = (key, img, key[1], key[2], key[3])
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
        if self.has_content():
            r = self.view.target(self.size()).intersected(QRectF(self.rect()))
            if not r.isEmpty():
                p.fillRect(r, self.checker)
        if self.cache is not None and self.has_content():
            key, img, scale, cx, cy = self.cache
            if key[1:] == self._key()[1:]:
                p.drawImage(0, 0, img)
            elif key[7] != self._key()[7]:
                pass        # (fills shown, outlines asked for, or the other way: wait for it)
            else:
                # moved or zoomed since it was drawn: show it moved and scaled to match
                f = self.view.scale / scale
                w, h = self.width(), self.height()
                left = w / 2 + (cx - self.view.cx) * self.view.scale - w / 2 * f
                top = h / 2 + (cy - self.view.cy) * self.view.scale - h / 2 * f
                p.drawImage(QRectF(left, top, w * f, h * f), img)
        if self.band is not None:
            # the rectangle being dragged: outside it dimmed, its edge dashed
            r = QRectF(self.band[0], self.band[1]).normalized()
            dim = QColor(0, 0, 0, 110)
            p.fillRect(QRectF(0, 0, self.width(), r.top()), dim)
            p.fillRect(QRectF(0, r.bottom(), self.width(), self.height() - r.bottom()), dim)
            p.fillRect(QRectF(0, r.top(), r.left(), r.height()), dim)
            p.fillRect(QRectF(r.right(), r.top(), self.width() - r.right(), r.height()), dim)
            pen = QPen(QColor(255, 255, 255), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            pen.setColor(QColor(0, 0, 0))
            pen.setDashOffset(4)
            p.setPen(pen)
            p.drawRect(r)
        if self.stroke is not None:
            # the stroke being dragged: where it erases (done when the button is let go)
            pen = QPen(QColor(220, 40, 40, 120), 2 * self.eraser, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if len(self.stroke) == 1:
                p.drawPoint(self.stroke[0])
            else:
                p.drawPolyline(self.stroke)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.erase_mode and self.mouse is not None and self.has_content():
            # the eraser: a circle as big as what it wipes out (light and dark, seen on anything)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for color, width in ((QColor(255, 255, 255, 220), 3), (QColor(0, 0, 0, 220), 1)):
                p.setPen(QPen(color, width))
                p.drawEllipse(self.mouse, self.eraser, self.eraser)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.message:
            p.setPen(self.palette().color(QPalette.ColorRole.Text))
            p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.message)
        p.setPen(QColor(90, 90, 90))
        p.drawText(8, 18, self.title)
        p.end()

    WHEEL_STEP = 80  # screen pixels moved for one notch of the wheel

    def wheelEvent(self, e):
        # The wheel moves the picture (Shift: sideways) and Ctrl+wheel zooms, as in Inkscape,
        # browsers and office programs: the wheel used to zoom, and a turn of it meant for the
        # settings panel beside zoomed the picture instead (the owner).
        d = e.angleDelta()
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = (d.y() or d.x()) / 120.0
            if steps:
                self.view.zoom(1.25 ** steps, e.position(), self.size())
            return
        px = e.pixelDelta()
        if not px.isNull():      # (a touchpad: the distance it says)
            dx, dy = float(px.x()), float(px.y())
        else:
            dx, dy = d.x() / 120.0 * self.WHEEL_STEP, d.y() / 120.0 * self.WHEEL_STEP
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier and not dx:
            dx, dy = dy, 0.0
        if (dx or dy) and self.has_content():
            self.view.move(dx, dy)

    def set_erase_mode(self, on):
        self.erase_mode = on
        self.stroke = None
        if on:
            self.crop_mode = False
            self.band = None
        self._cursor()
        self.update()

    def set_crop_mode(self, on):
        if on:
            self.erase_mode = False
            self.stroke = None
        self.crop_mode = on
        self.band = None
        self._cursor()
        self.update()

    def to_picture(self, point):
        """A widget point in picture pixels (not clamped)."""
        t = self.view.target(self.size())
        return QPointF((point.x() - t.x()) / self.view.scale, (point.y() - t.y()) / self.view.scale)

    def mousePressEvent(self, e):
        if self.erase_mode and e.button() == Qt.MouseButton.LeftButton and self.has_content():
            self.stroke = [e.position()]
            self.update()
            return
        if self.crop_mode and e.button() == Qt.MouseButton.LeftButton and self.has_content():
            self.band = [e.position(), e.position()]
            self.update()
            return
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.drag = e.position()
            self.press = e.position() if e.button() == Qt.MouseButton.LeftButton else None
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self.erase_mode:
            self.mouse = e.position()
            self.update()
        if not e.buttons() and self.has_content():
            self.hovered.emit(self.to_picture(e.position()))
        if self.stroke is not None:
            self.stroke.append(e.position())
            self.update()
            return
        if self.band is not None:
            self.band[1] = e.position()
            self.update()
            return
        if self.drag is not None:
            d = e.position() - self.drag
            self.drag = e.position()
            self.view.move(d.x(), d.y())

    def mouseReleaseEvent(self, e):
        if self.stroke is not None:
            stroke, self.stroke = self.stroke, None
            self.update()
            self.erased.emit(self.eraser / self.view.scale, [self.to_picture(q) for q in stroke])
            return
        press, self.press = getattr(self, "press", None), None
        if press is not None and self.band is None and (e.position() - press).manhattanLength() < 4 \
                and self.has_content():
            self.clicked.emit(self.to_picture(e.position()),
                              bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier))
        if self.band is not None:
            moved = (self.band[1] - self.band[0]).manhattanLength()
            a, b = self.to_picture(self.band[0]), self.to_picture(self.band[1])
            self.band = None
            self.update()
            # a click is no rectangle (rounded out to whole pixels, a click across a pixel's edge
            # made a 2 x 2 crop)
            self.cropped.emit(QRectF(a, b).normalized() if moved >= 4 else QRectF())
            return
        self.drag = None
        self._cursor()

    def leaveEvent(self, e):
        self.mouse = None
        self.hovered.emit(None)
        self.update()
        super().leaveEvent(e)

    def contextMenuEvent(self, e):
        if self.has_content():
            self.menu_requested.emit(self.to_picture(QPointF(e.pos())), e.globalPos())

    def resizeEvent(self, e):
        if self.view.fitted:
            self.view.fit(self.size())
        super().resizeEvent(e)
        self.redraw()


class Loader(QThread):
    """Reads a picture file in the background (a 12-megapixel PNG takes 0.8 s to decode: the
    window used to freeze that long)."""

    loaded = Signal(int, object, str)  # number, QImage, path
    failed = Signal(int, str)

    def __init__(self, number, path):
        super().__init__()
        self.number, self.path = number, path

    def run(self):
        try:
            self.loaded.emit(self.number, image.load(self.path), self.path)
        except Exception as e:
            self.failed.emit(self.number, str(e) or e.__class__.__name__)


class Saver(QThread):
    """Writes a PDF, EPS or DXF in the background."""

    done = Signal(object, str)  # the Saver, the error ("" if saved)

    def __init__(self, path, svg, fmt, size):
        super().__init__()
        self.path, self.svg, self.fmt, self.size = path, svg, fmt, size

    def run(self):
        try:
            export.write(self.path, self.svg, self.fmt, self.size)
            self.done.emit(self, "")
        except Exception as e:
            self.done.emit(self, str(e) or e.__class__.__name__)


class Job:
    def __init__(self, number, img, options, enlarge, want_preview, auto=False):
        self.number = number
        self.auto = auto  # pick the settings first (Auto settings)
        self.quick = False  # show a quick preview first (a big picture, settings that take a while)
        self.auto_info = None
        self.img = img
        self.options = options
        self.enlarge = enlarge
        self.want_preview = want_preview
        self.cancelled = False


class Worker(QThread):
    """Traces in the background (the engine doesn't hold Python's lock while it works)."""

    progress = Signal(int, float)
    auto_done = Signal(int, object, object)  # job number, Options picked, engine.AutoInfo
    quick_done = Signal(int, str)  # job number, the SVG of a small copy (a big picture's quick preview)
    done = Signal(int, object, object)  # job number, Result, preview QImage or None
    failed = Signal(int, str)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        job = self.job
        try:
            last = [0.0]

            def report(f):
                if f - last[0] >= 0.02:
                    last[0] = f
                    self.progress.emit(job.number, f)
                return job.cancelled

            if job.auto:
                job.options, job.auto_info = auto_options(job.img, job.options)
                job.enlarge = job.auto_info.enlarge or tracing.AUTO
                self.auto_done.emit(job.number, job.options, job.auto_info)
            if job.quick and not job.cancelled:
                svg = tracing.quick_trace(job.img, job.options)
                if svg is not None and not job.cancelled:
                    self.quick_done.emit(job.number, svg)
            preview = tracing.preview_image(job.img, job.options) if job.want_preview else None
            if job.cancelled:
                raise engine.Cancelled()
            result = tracing.trace_image(job.img, job.options, job.enlarge, report)
            self.done.emit(job.number, result, preview)
        except engine.Cancelled:
            self.failed.emit(job.number, "")
        except Exception as e:  # shown in the window, never a crash
            self.failed.emit(job.number, str(e) or e.__class__.__name__)


def auto_options(img, current):
    """The settings Auto picks for <img>: all of them (mode, colors, smoothing, background,
    threshold, and the curve settings at the values that suit it). Returns (Options,
    engine.AutoInfo); info.enlarge is Enlarge first (0: Auto)."""
    picked, info = engine.auto(*image.pixels(img))
    # the threshold only when Auto picks Black and white (the panel shows it only then; otherwise
    # the trace was made with another threshold than the one the panel keeps)
    threshold = picked.threshold if picked.mode == engine.BRIGHTNESS else current.threshold
    # (the color edits stay: they're the user's, for this picture)
    # (Snap shapes stays as it is: it's a choice about the result, not something a picture needs)
    return replace(picked, threshold=threshold, stack=True, invert=False, edits=current.edits,
                   snap=current.snap), info


def describe_auto(options, info):
    """What Auto picked, in a few words for the status bar."""
    if options.mode == engine.BRIGHTNESS:
        parts = [tr("black and white")]
    else:
        parts = [tr("%d colors") % options.scans]
        if info.photo:
            parts[0] += tr(" (a photo or painting: it has more)")
    if options.smooth:
        parts.append(tr("smoothed"))
    if options.remove_background:
        parts.append(tr("transparent background kept"))
    if getattr(info, "line_art", False):
        parts.append(tr("thin lines: enlarged %d times first") % info.enlarge)
    return tr("Auto: %s") % ", ".join(parts)


class Settings(QScrollArea):
    """The settings panel."""

    changed = Signal()
    size_changed = Signal()     # the saved size (nothing to trace again)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMinimumWidth(270)
        box = QWidget()
        lay = QVBoxLayout(box)

        self.auto = QPushButton(tr("Auto settings"))
        self.auto.setToolTip(tr("Pick the settings that suit this picture (you can change them after)"))
        lay.addWidget(self.auto)

        self.mode = QComboBox()
        for label, mode in MODES:
            self.mode.addItem(tr(label), mode)
        top = QFormLayout()
        top.addRow(tr("Mode"), self.mode)
        lay.addLayout(top)

        self.g_multi = QGroupBox(tr("Layers"))
        f = QFormLayout(self.g_multi)
        self.scans = QSpinBox(minimum=2, maximum=64, value=8)
        self.scans.setToolTip(tr("How many colors (count the background too)"))
        self.scans_label = QLabel(tr("Colors"))
        f.addRow(self.scans_label, self.scans)
        self.smooth = QCheckBox(tr("Smooth"), checked=True)
        self.smooth.setToolTip(tr("Even out noise and JPEG blotches first; edges stay sharp"))
        self.stack = QCheckBox(tr("Stack"), checked=True)
        self.stack.setToolTip(tr("Each layer also covers the layers above it, so no gaps show"))
        for w in (self.smooth, self.stack):
            f.addRow(w)
        self.remove_bg = QComboBox()
        self.remove_bg.addItem(tr("Keep"), engine.BG_KEEP)
        self.remove_bg.addItem(tr("Remove"), engine.BG_REMOVE)
        self.remove_bg.addItem(tr("Remove, also inside"), engine.BG_REMOVE_ALL)
        self.remove_bg.setToolTip(tr("Leave out the picture's background (the color around its edge):\n"
                                  "Remove: around the picture only (that color inside shapes stays)\n"
                                  "Remove, also inside: that color everywhere"))
        self.bg_label = QLabel(tr("Background"))
        f.addRow(self.bg_label, self.remove_bg)
        lay.addWidget(self.g_multi)

        self.colors = ColorsPanel()
        self.colors.changed.connect(self.changed)
        lay.addWidget(self.colors)

        self.g_single = QGroupBox(tr("Scan"))
        f = QFormLayout(self.g_single)
        self.threshold = QDoubleSpinBox(minimum=0.0, maximum=1.0, singleStep=0.05, decimals=2, value=0.45)
        self.threshold.setToolTip(tr("Black and white: everything darker than this is traced.\n"
                                  "Edges: higher finds fewer edges."))
        self.invert = QCheckBox(tr("Invert"))
        self.invert.setToolTip(tr("Trace the light parts instead"))
        f.addRow(tr("Threshold"), self.threshold)
        f.addRow(self.invert)
        lay.addWidget(self.g_single)

        self.g_potrace = QGroupBox(tr("Curves"))
        f = QFormLayout(self.g_potrace)
        self.speckles = QSpinBox(minimum=0, maximum=1000, value=2)
        self.speckles.setToolTip(tr("Drop spots of up to this many pixels"))
        self.corners = QDoubleSpinBox(minimum=0.0, maximum=1.34, singleStep=0.1, decimals=2, value=1.0)
        self.corners.setToolTip(tr("0 keeps every corner sharp; higher rounds them off"))
        self.optimize = QCheckBox(tr("Optimize"), checked=True)
        self.optimize.setToolTip(tr("Join curve segments: smaller files"))
        self.tolerance = QDoubleSpinBox(minimum=0.0, maximum=5.0, singleStep=0.1, decimals=2, value=0.2)
        self.tolerance.setToolTip(tr("How far joining segments may move the curve"))
        f.addRow(tr("Speckles"), self.speckles)
        f.addRow(tr("Smooth corners"), self.corners)
        f.addRow(self.optimize)
        f.addRow(tr("Tolerance"), self.tolerance)
        self.snap = QCheckBox(tr("Snap shapes"))
        self.snap.setToolTip(tr("Make (all but) straight edges straight, level and upright ones exactly level and "
                             "upright, and round shapes perfect circles and ellipses: for cutting, CAD and clean "
                             "logos (it can move an edge up to half a pixel)"))
        f.addRow(self.snap)
        lay.addWidget(self.g_potrace)

        self.g_auto = QGroupBox(tr("Autotrace"))
        f = QFormLayout(self.g_auto)
        self.error = QDoubleSpinBox(minimum=0.1, maximum=10.0, singleStep=0.25, decimals=2, value=2.0)
        self.error.setToolTip(tr("How far a curve may be from the outline, in pixels"))
        self.filters = QSpinBox(minimum=0, maximum=20, value=4)
        self.filters.setToolTip(tr("Smoothing passes on outlines before fitting curves"))
        self.width = QCheckBox(tr("Keep line widths"), checked=True)
        f.addRow(tr("Error threshold"), self.error)
        f.addRow(tr("Filter passes"), self.filters)
        f.addRow(self.width)
        lay.addWidget(self.g_auto)

        g = QGroupBox(tr("Size"))
        f = QFormLayout(g)
        self.enlarge = QComboBox()
        self.enlarge.addItem(tr("Auto"), tracing.AUTO)
        self.enlarge.addItem(tr("Off"), 1)
        self.enlarge.addItem(tr("2 times"), 2)
        self.enlarge.addItem(tr("4 times"), 4)
        self.enlarge.setToolTip(tr("Trace small pictures bigger, for smoother curves (the SVG keeps the picture's size)"))
        f.addRow(tr("Enlarge first"), self.enlarge)
        # the size it's saved at (SVG, PDF, EPS, DXF): changes only the file, not the trace
        self.size_unit = QComboBox()
        self.size_unit.addItem(tr("Picture's pixels"), export.PX)
        self.size_unit.addItem(tr("Inches"), export.IN)
        self.size_unit.addItem(tr("Millimeters"), export.MM)
        self.size_unit.setToolTip(tr("The width it's saved at; the height follows. Picture's pixels: the picture's own "
                                  "size, 96 pixels to the inch (as browsers, Inkscape and Illustrator count them)"))
        self.size_width = QDoubleSpinBox(minimum=0.01, maximum=100000.0, decimals=2, value=4.0)
        self.size_width.setToolTip(tr("The saved width, in the unit beside it (the height follows the picture)"))
        self.size_info = QLabel()
        self.size_info.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.size_width, 1)
        row.addWidget(self.size_unit, 1)
        f.addRow(tr("Saved width"), row)
        f.addRow(self.size_info)
        self.picture_px = None      # the picture's width in pixels (MainWindow sets it): for the first width
        lay.addWidget(g)

        self.reset = QPushButton(tr("Reset settings"))
        lay.addWidget(self.reset)
        lay.addStretch(1)
        self.setWidget(box)

        self._edge = 0.65
        self._bw = 0.45
        self._last_mode = engine.COLORS
        for w in (self.mode, self.enlarge, self.remove_bg):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.scans, self.speckles, self.filters):
            w.valueChanged.connect(self._changed)
        for w in (self.threshold, self.corners, self.tolerance, self.error):
            w.valueChanged.connect(self._changed)
        for w in (self.smooth, self.stack, self.invert, self.optimize, self.width, self.snap):
            w.toggled.connect(self._changed)
        self.reset.clicked.connect(self.reset_all)
        self._unit = export.PX
        self.size_unit.currentIndexChanged.connect(self._unit_changed)
        self.size_width.valueChanged.connect(lambda _v: self.size_changed.emit())
        self.size_width.setVisible(False)
        self._update_visible()
        # The panel's width never changes: its scroll bar is always there (grayed when there's
        # nothing to scroll). Coming and going (more colors, more rows of swatches) it made the
        # panel narrower and moved the settings under the mouse (the Colors arrows) sideways;
        # keeping room for it instead missed by a few pixels on some systems (its width depends
        # on the style).
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # and never narrower than what's in it (with fonts wider than these, it was: a scroll bar
        # across came and went with the rows of swatches, and the contents widened under the mouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # (what's in it needs more once a picture is traced, e.g. the swatches: worked out again
        # whenever its layout changes, and only ever wider, so it doesn't move back and forth)
        box.installEventFilter(self)
        # number boxes and lists change with the wheel only once clicked into (see eventFilter)
        for w in box.findChildren(QAbstractSpinBox) + box.findChildren(QComboBox):
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            w.installEventFilter(self)
        self._fit_contents()

    def _fit_contents(self):
        box = self.widget()
        box.ensurePolished()
        need = box.minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width() + 2 * self.frameWidth() + 4
        if need > self.minimumWidth():
            self.setMinimumWidth(need)

    def eventFilter(self, obj, event):
        if obj is self.widget() and event.type() == QEvent.Type.LayoutRequest:
            self._fit_contents()
        elif event.type() == QEvent.Type.Wheel and isinstance(obj, (QAbstractSpinBox, QComboBox)) \
                and not obj.hasFocus():
            # A number box or a list the mouse happens to be over, not clicked into: the wheel
            # scrolls the panel, it doesn't change the setting (the owner: scrolling down the
            # panel changed Colors, Speckles... on the way)
            QApplication.sendEvent(self.verticalScrollBar(), event)
            return True
        return super().eventFilter(obj, event)

    def current_mode(self):
        return self.mode.currentData()

    def _changed(self, *_):
        mode = self.current_mode()
        if mode != self._last_mode:
            # each of Black and white and Edges keeps its own threshold
            if self._last_mode == engine.EDGES:
                self._edge = self.threshold.value()
            elif self._last_mode == engine.BRIGHTNESS:
                self._bw = self.threshold.value()
            self._last_mode = mode
            if mode in (engine.EDGES, engine.BRIGHTNESS):
                self.threshold.blockSignals(True)
                self.threshold.setValue(self._edge if mode == engine.EDGES else self._bw)
                self.threshold.blockSignals(False)
            self._update_visible()
        self.tolerance.setEnabled(self.optimize.isChecked())
        self.changed.emit()

    def _update_visible(self):
        mode = self.current_mode()
        self.g_multi.setVisible(mode in MULTI_MODES or mode == engine.AUTOTRACE)
        self.smooth.setVisible(mode in (engine.COLORS, engine.GRAYS))
        self.stack.setVisible(mode in MULTI_MODES)
        self.remove_bg.setVisible(mode in MULTI_MODES or mode == engine.AUTOTRACE)
        self.bg_label.setVisible(mode in MULTI_MODES or mode == engine.AUTOTRACE)
        self.scans_label.setText({engine.GRAYS: tr("Grays"), engine.BRIGHTNESS_STEPS: tr("Steps")}.get(mode, tr("Colors")))
        self.g_single.setVisible(mode in (engine.BRIGHTNESS, engine.EDGES))
        self.g_potrace.setVisible(mode in POTRACE_MODES)
        self.g_auto.setVisible(mode in AUTOTRACE_MODES)
        self.width.setVisible(mode == engine.CENTERLINE)
        self.colors.setVisible(mode in tracing.COLOR_MODES)

    def options(self):
        return engine.Options(
            mode=self.current_mode(),
            scans=self.scans.value(),
            smooth=self.smooth.isChecked(),
            stack=self.stack.isChecked(),
            remove_background=self.remove_bg.currentData(),
            threshold=self.threshold.value(),
            invert=self.invert.isChecked(),
            speckles=self.speckles.value(),
            smooth_corners=self.corners.value(),
            optimize=self.optimize.isChecked(),
            optimize_tolerance=self.tolerance.value(),
            error_threshold=self.error.value(),
            filter_iterations=self.filters.value(),
            preserve_width=self.width.isChecked(),
            edits=self.colors.edits_tuple(),
            snap=engine.SNAP_ALL if self.snap.isChecked() else 0,
        )

    def enlarge_setting(self):
        return self.enlarge.currentData()

    # the saved size

    def saved_size(self):
        unit = self.size_unit.currentData()
        return export.Size(unit, self.size_width.value()) if unit != export.PX else export.PIXELS

    def set_saved_size(self, size):
        self.size_unit.blockSignals(True)
        self.size_width.blockSignals(True)
        self.size_unit.setCurrentIndex(max(0, self.size_unit.findData(size.unit)))
        if size.unit != export.PX:
            self.size_width.setValue(size.width)
        self._unit = size.unit
        self.size_width.setVisible(size.unit != export.PX)
        self.size_unit.blockSignals(False)
        self.size_width.blockSignals(False)
        self.size_changed.emit()

    def _unit_changed(self):
        """The same size in the new unit (from pixels: the picture's size at 96 to the inch)."""
        unit = self.size_unit.currentData()
        inches = None
        if self._unit == export.PX and self.picture_px:
            inches = self.picture_px / export.PX_PER_IN
        elif self._unit == export.IN:
            inches = self.size_width.value()
        elif self._unit == export.MM:
            inches = self.size_width.value() / export.MM_PER_IN
        if unit != export.PX and inches is not None:
            self.size_width.blockSignals(True)
            self.size_width.setValue(round(inches * (export.MM_PER_IN if unit == export.MM else 1.0), 2))
            self.size_width.blockSignals(False)
        self._unit = unit
        self.size_width.setVisible(unit != export.PX)
        self.size_changed.emit()

    # saved between runs
    _SAVED = ["mode", "scans", "smooth", "stack", "remove_bg", "threshold", "invert", "speckles", "corners",
              "optimize", "tolerance", "error", "filters", "width", "enlarge", "snap"]

    def _widgets(self):
        return [(name, getattr(self, name)) for name in self._SAVED]

    def save(self, qs):
        for name, w in self._widgets():
            if isinstance(w, QComboBox):
                qs.setValue("settings/" + name, w.currentIndex())
            elif isinstance(w, QCheckBox):
                qs.setValue("settings/" + name, int(w.isChecked()))
            else:
                qs.setValue("settings/" + name, w.value())
        qs.setValue("settings/edge_threshold", self._edge if self.current_mode() != engine.EDGES
                    else self.threshold.value())
        qs.setValue("settings/bw_threshold", self._bw if self.current_mode() != engine.BRIGHTNESS
                    else self.threshold.value())
        size = self.saved_size()
        qs.setValue("save/unit", size.unit)
        qs.setValue("save/width", self.size_width.value())

    def load(self, qs):
        for name, w in self._widgets():
            v = qs.value("settings/" + name)
            if v is None:
                continue
            w.blockSignals(True)
            try:
                if isinstance(w, QComboBox):
                    i = int(v)
                    if 0 <= i < w.count():
                        w.setCurrentIndex(i)
                elif isinstance(w, QCheckBox):
                    w.setChecked(bool(int(v)))
                elif isinstance(w, QSpinBox):
                    w.setValue(int(float(v)))
                else:
                    w.setValue(float(v))
            except (TypeError, ValueError):
                pass
            w.blockSignals(False)
        try:
            self._edge = float(qs.value("settings/edge_threshold", self._edge))
            self._bw = float(qs.value("settings/bw_threshold", self._bw))
        except (TypeError, ValueError):
            pass
        self._last_mode = self.current_mode()
        self.tolerance.setEnabled(self.optimize.isChecked())
        self._update_visible()
        try:
            unit = str(qs.value("save/unit", export.PX))
            width = float(qs.value("save/width", 4.0))
            self.size_width.blockSignals(True)
            self.size_width.setValue(width)     # (also kept while the unit is pixels)
            self.size_width.blockSignals(False)
            self.set_saved_size(export.Size(unit, width) if unit != export.PX else export.PIXELS)
        except (TypeError, ValueError):
            self.set_saved_size(export.PIXELS)

    # for Undo: every setting as it is, and put back

    def snapshot(self):
        values = []
        for name, w in self._widgets():
            if isinstance(w, QComboBox):
                values.append((name, w.currentIndex()))
            elif isinstance(w, QCheckBox):
                values.append((name, w.isChecked()))
            else:
                values.append((name, w.value()))
        return (tuple(values), self._edge, self._bw, self.colors.state())

    def restore(self, snap):
        """Put the settings of snapshot() back (without tracing: the caller traces)."""
        values, self._edge, self._bw, edits = snap
        widgets = dict(self._widgets())
        for name, v in values:
            w = widgets[name]
            w.blockSignals(True)
            if isinstance(w, QComboBox):
                w.setCurrentIndex(v)
            elif isinstance(w, QCheckBox):
                w.setChecked(v)
            else:
                w.setValue(v)
            w.blockSignals(False)
        self._last_mode = self.current_mode()
        self.tolerance.setEnabled(self.optimize.isChecked())
        self.colors.set_state(edits)
        self._update_visible()

    def apply_auto(self, o, enlarge=None):
        """Show the settings Auto picked (without tracing again: they're being traced): all of
        them, Enlarge first too (enlarge: its setting, tracing.AUTO by default)."""
        widgets = [w for _, w in self._widgets()]
        for w in widgets:
            w.blockSignals(True)
        index = [m for _, m in MODES].index(o.mode)
        self.mode.setCurrentIndex(index)
        self.scans.setValue(max(self.scans.minimum(), min(self.scans.maximum(), o.scans)))
        self.smooth.setChecked(o.smooth)
        self.stack.setChecked(o.stack)
        self.remove_bg.setCurrentIndex(max(0, self.remove_bg.findData(int(o.remove_background))))
        self.invert.setChecked(o.invert)
        if o.mode == engine.BRIGHTNESS:
            self.threshold.setValue(o.threshold)
            self._bw = o.threshold
        elif o.mode == engine.EDGES:
            self.threshold.setValue(self._edge)
        self.speckles.setValue(o.speckles)
        self.corners.setValue(o.smooth_corners)
        self.optimize.setChecked(o.optimize)
        self.tolerance.setValue(o.optimize_tolerance)
        self.tolerance.setEnabled(bool(o.optimize))
        self.error.setValue(o.error_threshold)
        self.filters.setValue(o.filter_iterations)
        self.width.setChecked(o.preserve_width)
        self.enlarge.setCurrentIndex(max(0, self.enlarge.findData(tracing.AUTO if enlarge is None else enlarge)))
        for w in widgets:
            w.blockSignals(False)
        self._last_mode = o.mode
        self._update_visible()

    def reset_all(self):
        widgets = [w for _, w in self._widgets()]
        for w in widgets:
            w.blockSignals(True)
        self.mode.setCurrentIndex(0)
        self.scans.setValue(8)
        self.smooth.setChecked(True)
        self.stack.setChecked(True)
        self.remove_bg.setCurrentIndex(0)
        self.threshold.setValue(0.45)
        self.invert.setChecked(False)
        self.speckles.setValue(2)
        self.corners.setValue(1.0)
        self.optimize.setChecked(True)
        self.tolerance.setValue(0.2)
        self.error.setValue(2.0)
        self.filters.setValue(4)
        self.width.setChecked(True)
        self.enlarge.setCurrentIndex(0)
        self.snap.setChecked(False)
        for w in widgets:
            w.blockSignals(False)
        self._edge, self._bw, self._last_mode = 0.65, 0.45, engine.COLORS
        self.tolerance.setEnabled(True)
        self._update_visible()
        self.colors.clear()
        self.changed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.qs = QSettings("Kanzonas", APP_NAME)
        self.img = None  # QImage, RGBA8888: the picture traced (cropped, if it is)
        self.full_img = None  # the whole picture opened
        self.crop = None  # QRect of full_img that img is, or None
        self.erased = ()  # (Erase on the picture) strokes: (radius, ((x, y), ...)) in full_img's pixels
        self.history = []  # Undo: (settings, crop) of each SVG traced for this picture
        self.history_at = -1
        self.source_path = None
        self.save_path = None
        self.savers = []  # Saver threads still writing
        self.batch = None  # the Convert many pictures dialog, once opened
        self.help = None  # the help window, once opened
        self.result = None  # tracing.Result
        self.preview = None  # QImage
        self.job_number = 0
        self.job = None
        self.worker = None
        self.pending = False
        self.pending_auto = False
        self.colors_key = None  # the picture and color settings of the last trace
        self.closing = False
        self.loader = None  # reading a picture file
        self.old_loaders = []  # replaced by a newer one, still finishing
        self.load_number = 0

        self.view = View()
        self.left = Canvas(self.view, tr("Picture"))
        self.left.cropped.connect(self.on_cropped)
        self.left.clicked.connect(self.on_picture_clicked)
        self.left.erased.connect(self.on_erased)
        self.right = Canvas(self.view, tr("SVG"))
        self.right.clicked.connect(self.on_picture_clicked)    # (the SVG: the same place in the picture)
        for side in (self.left, self.right):
            side.hovered.connect(self.on_hover)
            side.menu_requested.connect(self.on_picture_menu)
        self.hover_text = None  # what the status bar said before the mouse came over a color
        self.left.set_message(tr("Open a picture (Ctrl+O), drag one here, or paste one (Ctrl+V)."))
        split = QSplitter()
        split.addWidget(self.left)
        split.addWidget(self.right)
        split.setChildrenCollapsible(False)
        self.settings = Settings()
        self.tool_bar = self._make_tool_bar()
        sides = QWidget()
        lay = QVBoxLayout(sides)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.tool_bar)
        lay.addWidget(split, 1)
        outer = QSplitter()
        outer.addWidget(sides)
        outer.addWidget(self.settings)
        outer.setStretchFactor(0, 1)
        outer.setStretchFactor(1, 0)
        self.setCentralWidget(outer)

        self.status = QLabel()
        self.bar = QProgressBar(maximum=1000, textVisible=False)
        self.bar.setFixedWidth(160)
        self.bar.hide()
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(self.bar)

        self.timer = QTimer(self, singleShot=True, interval=150)
        self.timer.timeout.connect(self.start_trace)
        self.settings.changed.connect(self.settings_changed)
        self.settings.size_changed.connect(self._show_saved_size)
        self.settings.auto.clicked.connect(self.auto_settings)
        self.settings.load(self.qs)
        self.settings.colors.selection_changed.connect(self._selection_changed)
        self.settings.colors.menu_requested.connect(self._color_menu)

        self._make_menus()
        self.setAcceptDrops(True)
        self.resize(1300, 800)
        geo = self.qs.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._update_title()
        self._update_actions()

    # menus

    def _action(self, menu, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _make_menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("&File"))
        self.a_open = self._action(m, tr("Open picture..."), self.open_dialog, QKeySequence.StandardKey.Open)
        self.m_recent = m.addMenu(tr("Open recent"))
        self.m_recent.aboutToShow.connect(self._fill_recent)
        self._fill_recent()
        self.a_many = self._action(m, tr("Convert many pictures..."), lambda: self.convert_many(), "Ctrl+Shift+O")
        self.a_paste = self._action(m, tr("Paste picture"), self.paste, QKeySequence.StandardKey.Paste)
        m.addSeparator()
        self.a_save = self._action(m, tr("Save..."), self.save, QKeySequence.StandardKey.Save)
        # one command for each kind of file (the owner: picking the kind in the file dialog's
        # list was easy to miss)
        self.a_save_svg = self._action(m, tr("Save as SVG..."), lambda: self.save_as("svg"), "Ctrl+Shift+S")
        self.a_save_pdf = self._action(m, tr("Save as PDF..."), lambda: self.save_as("pdf"))
        self.a_save_eps = self._action(m, tr("Save as EPS..."), lambda: self.save_as("eps"))
        self.a_save_dxf = self._action(m, tr("Save as DXF..."), lambda: self.save_as("dxf"))
        self.a_save_dxf.setToolTip(tr("For CAD, laser and cutting programs: a layer for each color"))
        self.save_actions = [self.a_save_svg, self.a_save_pdf, self.a_save_eps, self.a_save_dxf]
        self.a_copy = self._action(m, tr("Copy SVG"), self.copy_svg, "Ctrl+Shift+C")
        m.addSeparator()
        self._action(m, tr("Quit"), self.close, QKeySequence.StandardKey.Quit)

        m = mb.addMenu(tr("&Edit"))
        self.a_undo = self._action(m, tr("Undo"), self.undo, QKeySequence.StandardKey.Undo)
        self.a_redo = self._action(m, tr("Redo"), self.redo, QKeySequence.StandardKey.Redo)

        m = mb.addMenu(tr("&View"))
        self.a_colors = self._action(m, tr("Show colors to trace"), self.show_colors_changed, "Ctrl+T", True)
        self.a_outlines = self._action(m, tr("Show outlines"), self.show_outlines_changed, "Ctrl+L", True)
        if int(self.qs.value("view/outlines", 0)):
            self.a_outlines.setChecked(True)
            self.right.set_outlines(True)
        m.addSeparator()
        self.a_zoom_in = self._action(m, tr("Zoom in"), lambda: self.view.zoom(1.25), QKeySequence.StandardKey.ZoomIn)
        self.a_zoom_out = self._action(m, tr("Zoom out"), lambda: self.view.zoom(0.8), QKeySequence.StandardKey.ZoomOut)
        self.a_fit = self._action(m, tr("Zoom to fit"), lambda: self.view.fit(self.left.size()), "Ctrl+0")
        self.a_actual = self._action(m, tr("Actual size"), self.actual_size, "Ctrl+1")
        m.addSeparator()
        self.a_collapse = self._action(m, tr("Collapse the ribbon"), lambda on: self.ribbon.set_collapsed(on),
                                       "Ctrl+F1", True)
        lang_menu = m.addMenu(tr("Language"))
        from PySide6.QtGui import QActionGroup
        group = QActionGroup(self)
        wanted = str(self.qs.value("view/language", "auto") or "auto")
        self.language_actions = {}
        for code, label in (("auto", tr("Automatic (the system's)")), ("en", "English"), ("es", "Español")):
            a = lang_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(code == wanted)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, code=code: self.set_language(code))
            self.language_actions[code] = a

        m = mb.addMenu(tr("&Trace"))
        self.a_auto = self._action(m, tr("Update automatically"), self.auto_changed, None, True)
        self.a_auto.setChecked(bool(int(self.qs.value("trace/auto", 1))))
        self.a_update = self._action(m, tr("Update now"), lambda: self.start_trace(), "F5")
        m.addSeparator()
        self.a_auto_settings = self._action(m, tr("Auto settings"), self.auto_settings, "Ctrl+Shift+A")
        self.a_auto_new = self._action(m, tr("Auto settings for new pictures"), self.auto_new_changed, None, True)
        self.a_auto_new.setChecked(bool(int(self.qs.value("trace/auto_new", 1))))
        self.a_reset = self._action(m, tr("Reset settings"), self.settings.reset_all)
        m.addSeparator()
        # the tools: what a click or a drag on the picture does (one at a time)
        self.a_select = self._action(m, tr("Select colors"), lambda _on=False: self.set_tool("select"), None, True)
        self.a_select.setToolTip(tr("Click a color on the picture or the SVG to select it (Ctrl+click: more), "
                                    "then change, merge or leave it out"))
        self.a_crop = self._action(m, tr("Crop picture"), lambda on: self.set_tool("crop" if on else "select"),
                                   "Ctrl+R", True)
        self.a_crop.setToolTip(tr("Drag across the part of the picture to trace"))
        self.a_uncrop = self._action(m, tr("Remove crop"), self.remove_crop, "Ctrl+Shift+R")
        self.a_erase = self._action(m, tr("Erase on the picture"),
                                    lambda on: self.set_tool("erase" if on else "select"), "Ctrl+E", True)
        self.a_erase.setToolTip(tr("Drag on the picture to wipe out what shouldn't be traced"))
        self.a_smaller = self._action(m, tr("Smaller eraser"), lambda: self.eraser_size(1 / 1.5), "[")
        self.a_bigger = self._action(m, tr("Bigger eraser"), lambda: self.eraser_size(1.5), "]")
        self.a_unerase = self._action(m, tr("Restore the picture"), self.restore_picture, "Ctrl+Shift+E")

        # the color edits (the Colors box's buttons, and a right-click on the picture, the SVG
        # or a swatch)
        m = mb.addMenu(tr("&Colors"))
        colors = self.settings.colors
        self.a_change = self._action(m, tr("Change color..."), lambda: colors.change_color())
        self.a_change.setToolTip(colors.b_change.toolTip())
        self.a_merge = self._action(m, tr("Merge colors..."), lambda: colors.merge(where=self._menu_at()))
        self.a_merge.setToolTip(colors.b_merge.toolTip())
        self.a_leave_out = self._action(m, tr("Leave out"), colors.leave_out, "Delete")
        self.a_leave_out.setToolTip(colors.b_out.toolTip())
        self.a_reset_colors = self._action(m, tr("Reset colors"), colors.reset)
        self.a_reset_colors.setToolTip(colors.b_reset.toolTip())
        m.addSeparator()
        self.a_select_none = self._action(m, tr("Select no color"), colors.select_none)
        self.color_actions = [self.a_change, self.a_merge, self.a_leave_out, self.a_reset_colors]

        m = mb.addMenu(tr("&Help"))
        self.a_help = self._action(m, tr("How to use KanzonasSVG"), self.show_help, QKeySequence.StandardKey.HelpContents)
        m.addSeparator()
        self.a_check = self._action(m, tr("Check for updates..."), self.check_updates)
        self.a_auto_updates = self._action(m, tr("Check for updates automatically"), self.auto_updates_changed, None, True)
        self.a_auto_updates.setChecked(self.updater().enabled())
        m.addSeparator()
        self.a_about = self._action(m, tr("About KanzonasSVG"), self.about)
        self._make_ribbon()
        self.set_tool("select")

    def _menu_at(self):
        """Where a menu opened by a command goes: under the mouse."""
        from PySide6.QtGui import QCursor
        return QCursor.pos()

    # the ribbon (built from the menus' commands: their names, shortcuts, checks and grayed
    # states stay the same in both)

    ICONS = {
        "a_open": "folder-open-outline", "a_paste": "content-paste", "a_many": "image-multiple-outline",
        "a_save": "content-save-outline", "a_save_svg": "vector-curve", "a_save_pdf": "file-pdf-box",
        "a_save_eps": "file-export-outline", "a_save_dxf": "vector-polyline", "a_copy": "content-copy",
        "a_undo": "undo", "a_redo": "redo", "a_auto_settings": "auto-fix", "a_update": "refresh",
        "a_auto": "sync", "a_auto_new": "image-filter-center-focus", "a_reset": "backup-restore",
        "a_select": "cursor-default-click-outline", "a_crop": "crop", "a_uncrop": "crop-free",
        "a_erase": "eraser", "a_smaller": "minus-circle-outline", "a_bigger": "plus-circle-outline",
        "a_unerase": "restore", "a_change": "format-color-fill", "a_merge": "merge",
        "a_leave_out": "eye-off-outline", "a_reset_colors": "palette-outline", "a_select_none": "selection-off",
        "a_colors": "palette-outline", "a_outlines": "vector-square", "a_zoom_in": "magnify-plus-outline",
        "a_zoom_out": "magnify-minus-outline", "a_fit": "fit-to-screen-outline", "a_actual": "numeric-1-box-outline",
        "a_help": "help-circle-outline", "a_check": "update", "a_about": "information-outline",
    }

    # the ribbon's shorter names (the menus keep the full ones)
    def _ribbon_names(self):
        return {
            "a_open": tr("Open"), "a_paste": tr("Paste"), "a_many": tr("Convert many"), "a_save": tr("Save"),
            "a_save_svg": tr("Save as SVG"), "a_save_pdf": tr("Save as PDF"), "a_save_eps": tr("Save as EPS"),
            "a_save_dxf": tr("Save as DXF"), "a_copy": tr("Copy SVG"), "a_auto_settings": tr("Auto settings"),
            "a_update": tr("Update now"), "a_auto": tr("Update automatically"), "a_auto_new": tr("Auto for new pictures"),
            "a_reset": tr("Reset settings"), "a_select": tr("Select colors"), "a_crop": tr("Crop"),
            "a_uncrop": tr("Remove crop"), "a_erase": tr("Erase"), "a_smaller": tr("Smaller"), "a_bigger": tr("Bigger"),
            "a_unerase": tr("Restore the picture"), "a_change": tr("Change color"), "a_merge": tr("Merge"),
            "a_leave_out": tr("Leave out"), "a_reset_colors": tr("Reset colors"), "a_select_none": tr("Select none"),
            "a_colors": tr("Colors to trace"), "a_outlines": tr("Outlines"), "a_zoom_in": tr("Zoom in"),
            "a_zoom_out": tr("Zoom out"), "a_fit": tr("Fit"), "a_actual": tr("Actual size"), "a_help": tr("Help"),
            "a_check": tr("Check for updates"), "a_about": tr("About"),
        }

    def _make_ribbon(self):
        from PySide6.QtWidgets import QToolBar, QToolButton
        from kanzonassvg import icons
        from kanzonassvg.ribbon import Ribbon, Stack, split_button, ROWS, SMALL_HEIGHT, LARGE_ICON
        names = self._ribbon_names()
        for attr, name in self.ICONS.items():
            a = getattr(self, attr)
            a.setIcon(icons.icon(name))
            a.setIconText(names.get(attr, a.text()))
            a.setIconVisibleInMenu(False)
        # Open, with the pictures opened last under its arrow
        self.b_open = QToolButton()
        self.b_open.setDefaultAction(self.a_open)
        self.b_open.setMenu(self.m_recent)
        self.b_open.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.b_open.setAutoRaise(True)
        self.b_open.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.b_open.setIconSize(QSize(LARGE_ICON, LARGE_ICON))
        self.b_open.setFixedHeight(ROWS * SMALL_HEIGHT)
        self.b_open.setToolTip(tr("Open a picture (the arrow: the pictures opened last)"))
        save_as = split_button(self.save_actions, large=True)
        r = self.ribbon = Ribbon()
        r.add_tab(tr("Home"), [
            (tr("File"), "large", [self.b_open, Stack([self.a_paste, self.a_many])]),
            (tr("Save"), "large", [self.a_save, save_as, Stack([self.a_copy])]),
            (tr("Edit"), "small", [self.a_undo, self.a_redo]),
            (tr("Trace"), "large", [self.a_auto_settings, Stack([self.a_update, self.a_auto]),
                                    Stack([self.a_auto_new, self.a_reset])]),
            (tr("Tools"), "large", [self.a_select, self.a_crop, self.a_erase]),
        ])
        r.add_tab(tr("Picture"), [
            (tr("Tools"), "large", [self.a_select, self.a_crop, self.a_erase]),
            (tr("Colors"), "large", [self.a_change, self.a_merge, self.a_leave_out,
                                     Stack([self.a_reset_colors, self.a_select_none])]),
            (tr("Crop"), "small", [self.a_uncrop]),
            (tr("Eraser"), "small", [self.a_smaller, self.a_bigger, self.a_unerase]),
        ])
        r.add_tab(tr("View"), [
            (tr("Zoom"), "small", [self.a_zoom_in, self.a_zoom_out, self.a_fit, self.a_actual]),
            (tr("Show"), "small", [self.a_colors, self.a_outlines]),
            (tr("Help"), "large", [self.a_help, Stack([self.a_check, self.a_about])]),
        ])
        r.set_group_names(True)
        bar = self.ribbon_bar = QToolBar(tr("Ribbon"))
        bar.setObjectName("ribbon")
        bar.setMovable(False)
        bar.toggleViewAction().setVisible(False)
        bar.layout().setContentsMargins(0, 0, 0, 0)
        bar.addWidget(r)
        self.addToolBar(bar)
        tab = self.qs.value("view/ribbon_tab", 0)
        try:
            r.setCurrentIndex(max(0, min(int(tab), r.count() - 1)))
        except (TypeError, ValueError):
            pass
        r.currentChanged.connect(lambda i: self.qs.setValue("view/ribbon_tab", i))
        r.collapsedChanged.connect(self._ribbon_collapsed)
        if int(self.qs.value("view/ribbon_collapsed", 0) or 0):
            self.a_collapse.setChecked(True)

    def _ribbon_collapsed(self, on):
        self.qs.setValue("view/ribbon_collapsed", int(on))
        if self.a_collapse.isChecked() != on:
            self.a_collapse.blockSignals(True)
            self.a_collapse.setChecked(on)
            self.a_collapse.blockSignals(False)

    def _update_actions(self):
        has = self.result is not None
        self.a_save.setEnabled(has)
        for a in self.save_actions:
            a.setEnabled(has)
        self.a_copy.setEnabled(has)
        self.a_crop.setEnabled(self.img is not None)
        self.a_undo.setEnabled(self.history_at > 0)
        self.a_redo.setEnabled(self.history_at + 1 < len(self.history))
        self.a_uncrop.setEnabled(self.crop is not None)
        self.a_erase.setEnabled(self.img is not None)
        self.a_unerase.setEnabled(bool(self.erased))

    def _update_title(self):
        name = os.path.basename(self.source_path) if self.source_path else None
        self.setWindowTitle("%s - %s" % (name, APP_NAME) if name else APP_NAME)

    # opening

    def open_dialog(self):
        start = self.qs.value("paths/open", os.path.expanduser("~"))
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Open picture"), start, picture_filter())
        if len(paths) == 1:
            self.open_path(paths[0])
        elif paths:
            self.qs.setValue("paths/open", os.path.dirname(os.path.abspath(paths[0])))
            self.convert_many(paths)        # (several: to convert them all)

    def convert_many(self, files=()):
        """File > Convert many pictures...: the dialog (one; more pictures are added to it)."""
        from kanzonassvg.batch import BatchDialog
        if self.batch is None:
            self.batch = BatchDialog(self, files)
        else:
            self.batch.add_files(files)
        self.batch.show()
        self.batch.raise_()
        self.batch.activateWindow()
        return self.batch

    def open_path(self, path):
        """Open a picture: the quick checks now (a message at once if it can't be read), the
        reading itself in the background. Returns whether it's being opened."""
        try:
            image.check(path)
        except image.ImageError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return False
        self.qs.setValue("paths/open", os.path.dirname(os.path.abspath(path)))
        self.load_number += 1
        if self.loader is not None:
            self.old_loaders.append(self.loader)
        self.loader = Loader(self.load_number, os.path.abspath(path))
        self.loader.loaded.connect(self.on_loaded)
        self.loader.failed.connect(self.on_load_failed)
        self.loader.finished.connect(self.on_loader_finished)
        self.status.setText(tr("Opening %s...") % os.path.basename(path))
        self.loader.start()
        return True

    def loading(self):
        return self.loader is not None and self.loader.isRunning()

    def on_loaded(self, number, img, path):
        if number == self.load_number and not self.closing:
            self.set_image(img, path)
            self.remember_recent(path)

    # File > Open recent: the last pictures opened, newest first

    RECENT = 10

    def recent_files(self):
        v = self.qs.value("recent/files", [])
        if isinstance(v, str):          # (QSettings gives one item back as a string)
            v = [v]
        return [str(p) for p in (v or []) if p][:self.RECENT]

    def remember_recent(self, path):
        path = os.path.abspath(path)
        files = [path] + [p for p in self.recent_files() if os.path.normcase(p) != os.path.normcase(path)]
        self.qs.setValue("recent/files", files[:self.RECENT])

    def _fill_recent(self):
        self.m_recent.clear()
        files = self.recent_files()
        for i, path in enumerate(files):
            # (an & in a name would underline the next letter: doubled)
            a = self.m_recent.addAction("&%d %s" % ((i + 1) % 10, os.path.basename(path).replace("&", "&&")))
            a.setToolTip(path)
            a.setStatusTip(path)
            a.triggered.connect(lambda _c=False, p=path: self.open_recent(p))
        if files:
            self.m_recent.addSeparator()
            self.m_recent.addAction(tr("Clear the list"), self.clear_recent)
        else:
            self.m_recent.addAction(tr("No pictures yet")).setEnabled(False)
        self.m_recent.menuAction().setEnabled(True)

    def open_recent(self, path):
        if not os.path.isfile(path):
            self.qs.setValue("recent/files", [p for p in self.recent_files() if p != path])
            QMessageBox.warning(self, APP_NAME, tr("%s isn't there any more (it was moved, renamed or deleted); "
                                "it's off the list now.") % path)
            return False
        return self.open_path(path)

    def clear_recent(self):
        self.qs.setValue("recent/files", [])

    def on_load_failed(self, number, message):
        if number == self.load_number and not self.closing:
            self.status.setText("")
            QMessageBox.warning(self, APP_NAME, message)

    def on_loader_finished(self):
        for t in [t for t in self.old_loaders if t.isFinished()]:
            self.old_loaders.remove(t)

    def paste(self):
        md = QGuiApplication.clipboard().mimeData()
        img = None
        if md is not None and md.hasImage():
            img = QImage(md.imageData())
        elif md is not None and md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    return self.open_path(url.toLocalFile())
        if img is None or img.isNull():
            QMessageBox.information(self, APP_NAME, tr("There's no picture on the clipboard. Copy a picture first."))
            return False
        try:
            self.set_image(image.to_rgba(img), None)
        except image.ImageError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return False
        return True

    def set_image(self, img, path):
        """A new picture: opened, pasted or dropped."""
        self.full_img = img
        self.crop = None
        self.erased = ()
        self.history, self.history_at = [], -1     # (Undo is for this picture)
        self.settings.colors.clear()    # (color edits are for the picture they were made on)
        self.source_path = path
        self.save_path = None
        self._show_picture(img)
        self.set_tool("select")     # (a new picture: clicks select colors again)

    def _show_picture(self, img, auto=None):
        """Trace img (the picture, or the part of it cropped to) as a new picture (auto: run Auto
        settings; by default as Auto settings for new pictures says)."""
        self.img = img
        self.result = None
        self.preview = None
        self.view.set_picture(img.width(), img.height())
        self.view.fit(self.left.size())
        self.left.set_message("")
        self.left.set_picture(img)
        self.right.set_svg("")
        self.right.set_message("")
        self._update_title()
        self._update_actions()
        self.right.title = tr("SVG")
        self.start_trace(auto=self.a_auto_new.isChecked() if auto is None else auto)

    # Undo: every SVG traced for this picture, with the settings and crop it was traced with

    def _state(self):
        c = self.crop
        return (self.settings.snapshot(), None if c is None else (c.x(), c.y(), c.width(), c.height()), self.erased)

    def remember(self):
        """The SVG shown is done: remember how it was made (unless more changes are on their way,
        or it's the one remembered last: Undo and Redo trace those again)."""
        if self.timer.isActive() or self.pending or self.restoring:
            return
        state = self._state()
        if self.history_at >= 0 and self.history[self.history_at] == state:
            return
        del self.history[self.history_at + 1:]
        self.history.append(state)
        self.history_at = len(self.history) - 1
        self._update_actions()

    restoring = False

    def _restore(self, at):
        if not (0 <= at < len(self.history)) or self.full_img is None:
            return
        self.history_at = at
        snap, crop, erased = self.history[at]
        self.cancel_crop()
        self.restoring = True
        try:
            self.settings.restore(snap)
            self.settings.save(self.qs)
            new_crop = None if crop is None else QRect(*crop)
            if new_crop != self.crop:
                self.crop, self.erased = new_crop, erased
                self._show_picture(self.picture_now(), auto=False)
            elif erased != self.erased:
                self.erased = erased
                self._update_picture(self.picture_now())
            else:
                self.start_trace()
        finally:
            self.restoring = False
        self._update_actions()

    def undo(self):
        self._restore(self.history_at - 1)

    def redo(self):
        self._restore(self.history_at + 1)

    def on_picture_clicked(self, point, add=False):
        """A click on the picture or the SVG: select the color traced there in the Colors panel
        (add: Ctrl held, add it to the selection or take it out)."""
        colors = self.settings.colors
        if self.img is None or not colors.isVisible() or not colors.palette:
            return
        x, y = int(point.x()), int(point.y())
        if not (0 <= x < self.img.width() and 0 <= y < self.img.height()):
            return
        c = self.img.pixelColor(x, y)
        if c.alpha() < 128:
            c = QColor(255, 255, 255)   # (transparent parts are traced as white)
        in_bg = self.result is not None and self.result.in_background(x, y)
        g = colors.select_at((c.red(), c.green(), c.blue()), add, in_bg)
        if g is not None:
            n = len(colors._selected_groups())
            unselected = add and not set(g.members) & colors.selected
            if g.background:
                said = tr("Unselected the background, %s in Colors (%s)") if unselected \
                    else tr("Selected the background, %s in Colors (%s)")
            else:
                said = tr("Unselected %s in Colors (%s)") if unselected else tr("Selected %s in Colors (%s)")
            how = tr("left out") if g.left_out else tr("%d%% of the picture") % round(100.0 * g.count / colors.total())
            self.status.setText(said % ("#%02x%02x%02x" % g.color, how)
                                + (tr("; %d colors selected") % n if n > 1 else "") + ".")

    # cropping

    # the tools: what a click or a drag on the picture does. One at a time: Select colors (a click
    # selects the color there; a drag moves the picture), Crop picture, Erase on the picture. The
    # bar above the two sides says what the one on does, with its controls (the owner: the tools
    # weren't clear: nothing said which one was on or how it worked).

    def set_tool(self, name):
        if self.img is None and name != "select":
            name = "select"
        self.tool = name
        for a, n in ((self.a_select, "select"), (self.a_crop, "crop"), (self.a_erase, "erase")):
            a.blockSignals(True)
            a.setChecked(n == name)
            a.blockSignals(False)
        self.left.set_crop_mode(name == "crop")
        self.left.set_erase_mode(name == "erase")
        if name == "erase":
            self.eraser_slider.blockSignals(True)
            self.eraser_slider.setValue(2 * self.left.eraser)
            self.eraser_slider.blockSignals(False)
        self._update_tool_bar()

    def _make_tool_bar(self):
        from PySide6.QtWidgets import QFrame, QHBoxLayout, QSlider, QToolButton
        bar = QFrame()
        bar.setObjectName("toolHint")
        bar.setFrameShape(QFrame.Shape.StyledPanel)
        bar.setAutoFillBackground(True)
        pal = bar.palette()
        pal.setColor(QPalette.ColorRole.Window, pal.color(QPalette.ColorRole.AlternateBase))
        bar.setPalette(pal)
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 3, 8, 3)
        self.tool_label = QLabel()
        self.tool_label.setWordWrap(True)
        self.tool_label.setTextFormat(Qt.TextFormat.RichText)
        # (two lines, always: a label that wraps in a row is given the height of one, and cut)
        self.tool_label.setFixedHeight(2 * self.tool_label.fontMetrics().lineSpacing() + 4)
        row.addWidget(self.tool_label, 1)

        def button(action=None, text=None, slot=None):
            b = QToolButton()
            if action is not None:
                b.setDefaultAction(action)
            else:
                b.setText(text)
                b.clicked.connect(slot)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setAutoRaise(False)
            row.addWidget(b)
            return b

        # (filled in by _make_ribbon's actions once they exist: see _fill_tool_bar)
        self.tool_row = row
        self.tool_button = button
        self.eraser_size_label = QLabel(tr("Size"))
        row.addWidget(self.eraser_size_label)
        self.eraser_slider = QSlider(Qt.Orientation.Horizontal)
        self.eraser_slider.setRange(4, 400)
        self.eraser_slider.setFixedWidth(140)
        self.eraser_slider.setToolTip(tr("The eraser's size, in pixels on the screen ([ smaller, ] bigger)"))
        self.eraser_slider.valueChanged.connect(self._eraser_slider_moved)
        row.addWidget(self.eraser_slider)
        return bar

    def _fill_tool_bar(self):
        b = self.tool_button
        self.tb_select = [b(self.a_change), b(self.a_merge), b(self.a_leave_out)]
        self.tb_erase = [self.eraser_size_label, self.eraser_slider, b(self.a_unerase)]
        self.tb_done = b(text=tr("Done"), slot=lambda: self.set_tool("select"))
        self.tb_done.setToolTip(tr("Back to selecting colors (Esc)"))

    def _update_tool_bar(self):
        if not hasattr(self, "tb_select"):
            self._fill_tool_bar()
        tool = getattr(self, "tool", "select")
        colors = self.settings.colors
        has_colors = colors.isVisible() or (self.img is not None and self.settings.current_mode() in tracing.COLOR_MODES)
        for w in self.tb_select:
            w.setVisible(tool == "select" and has_colors and self.img is not None)
        for w in self.tb_erase:
            w.setVisible(tool == "erase")
        self.tb_done.setVisible(tool != "select")
        self.tb_done.setText(tr("Cancel") if tool == "crop" else tr("Done"))
        if tool == "crop":
            text = tr("<b>Crop picture</b>: drag across the part of the picture to trace (on the left). Esc cancels.")
        elif tool == "erase":
            text = tr("<b>Erase on the picture</b>: drag on the picture (on the left) to wipe out what shouldn't "
                      "be traced. The circle shows the eraser. Undo takes a stroke back; the file never changes.")
        elif self.img is None:
            text = tr("Open a picture (Ctrl+O), drag one here, or paste one (Ctrl+V).")
        elif not has_colors:
            text = tr("<b>Select colors</b>: this mode traces one color, so there are no colors to select. "
                      "Drag to move the picture; Ctrl+wheel zooms.")
        else:
            picked = colors._selected_groups()
            if not picked:
                text = tr("<b>Select colors</b>: click a color on the picture or the SVG to select it (Ctrl+click "
                          "selects more), then change it, merge it or leave it out. Right-click for the same.")
            elif len(picked) == 1:
                g = picked[0]
                share = 100.0 * g.count / max(1, colors.total())
                text = tr("<b>%s</b> selected (%.1f%% of the picture), marked on the SVG. Ctrl+click another "
                          "color to merge them; Esc selects none.") % (colorbox(g.color) + " #%02x%02x%02x" % g.color, share)
            else:
                text = tr("<b>%d colors</b> selected, marked on the SVG. Merge them into one, change them, or "
                          "leave them out; Esc selects none.") % len(picked)
        self.tool_label.setText(text)

    def _eraser_slider_moved(self, value):
        self.left.eraser = max(2, min(200, value // 2))
        self.left.update()

    def _selection_changed(self):
        colors = self.settings.colors
        change, merge, out, put_back, reset = colors.can()
        self.a_change.setEnabled(change)
        self.a_merge.setEnabled(merge)
        self.a_leave_out.setEnabled(out)
        self.a_leave_out.setText(tr("Put back") if put_back else tr("Leave out"))
        self.a_leave_out.setIconText(self.a_leave_out.text())
        self.a_reset_colors.setEnabled(reset)
        self.a_select_none.setEnabled(bool(colors.selected))
        self._update_mark()
        self._update_tool_bar()

    def _update_mark(self):
        """The selected colors marked on the SVG (the rest faded)."""
        chosen = self.settings.colors.selected_colors() if self.settings.colors.isVisible() else []
        if self.result is None or not chosen or not self.settings.colors.selected:
            self.right.set_mark(None)
            return
        self.right.set_mark(chosen)

    def _color_at(self, point):
        """The Colors box's swatch for the picture's pixel at point, or None."""
        colors = self.settings.colors
        if self.img is None or not colors.isVisible() or not colors.palette:
            return None
        x, y = int(point.x()), int(point.y())
        if not (0 <= x < self.img.width() and 0 <= y < self.img.height()):
            return None
        c = self.img.pixelColor(x, y)
        if c.alpha() < 128:
            c = QColor(255, 255, 255)   # (transparent parts are traced as white)
        in_bg = self.result is not None and self.result.in_background(x, y)
        return colors.group_at((c.red(), c.green(), c.blue()), in_bg)

    def on_hover(self, point):
        """The mouse over the picture or the SVG (Select colors): say what a click there selects."""
        pointing = getattr(self, "tool", "select") == "select" and self.settings.colors.isVisible() \
            and bool(self.settings.colors.palette)
        self.left.set_pointing(pointing)
        self.right.set_pointing(pointing)
        g = self._color_at(point) if (point is not None and pointing) else None
        if g is None:
            if self.hover_text is not None:
                self.status.setText(self.hover_text)
                self.hover_text = None
            return
        if self.hover_text is None:
            self.hover_text = self.status.text()
        colors = self.settings.colors
        how = tr("left out") if g.left_out else tr("%.1f%% of the picture") % (100.0 * g.count / max(1, colors.total()))
        what = tr("the background, #%02x%02x%02x") % g.color if g.background else "#%02x%02x%02x" % g.color
        self.status.setText(tr("Click: select %s (%s). Ctrl+click: add it. Right-click: the color commands.") % (what, how))

    def on_picture_menu(self, point, where):
        """A right-click on the picture or the SVG: the color there selected (if it wasn't), and
        the color commands."""
        g = self._color_at(point)
        if g is not None and not set(g.members) & self.settings.colors.selected:
            self.settings.colors.click_group(g)
        self._color_menu(where)

    def _color_menu(self, where):
        menu = QMenu(self)
        if self.settings.colors.isVisible() and self.settings.colors.palette:
            menu.addActions(self.color_actions)
            menu.addAction(self.a_select_none)
            menu.addSeparator()
        menu.addActions([self.a_crop, self.a_erase])
        if self.crop is not None:
            menu.addAction(self.a_uncrop)
        if self.erased:
            menu.addAction(self.a_unerase)
        self.open_menu(menu, where)

    def open_menu(self, menu, where):
        """Show a right-click menu (a test answers it instead)."""
        self.menu_shown = menu
        menu.exec(where)

    def start_crop(self):
        self.set_tool("crop")
        if self.tool == "crop":
            self.status.setText(tr("Drag across the picture on the left to crop it (Esc: cancel)."))

    def cancel_crop(self):
        if self.left.crop_mode:
            self.set_tool("select")
            return True
        return False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if getattr(self, "tool", "select") != "select":
                self.set_tool("select")
                self.status.setText("")
                return
            if self.settings.colors.selected:
                self.settings.colors.select_none()
                return
        super().keyPressEvent(e)

    def on_cropped(self, rect):
        """The rectangle dragged (picture pixels of what's shown): trace only that part."""
        self.set_tool("select")
        if self.img is None:
            return
        r = rect.toAlignedRect().intersected(QRect(0, 0, self.img.width(), self.img.height()))
        if r.width() < 2 or r.height() < 2:
            self.status.setText(tr("Too small to crop to: drag across the part to trace."))
            return
        self.crop_to(r)

    def crop_to(self, r):
        """Crop to r, a QRect of the picture shown (which may be cropped already)."""
        if self.crop is not None:
            r = r.translated(self.crop.topLeft())
        self.crop = r
        self._show_picture(self.picture_now())

    def remove_crop(self):
        if self.crop is None or self.full_img is None:
            return
        self.cancel_crop()
        self.crop = None
        self._show_picture(self.picture_now())

    # erasing parts of the picture (they're traced as see-through, as a transparent picture's are)

    def picture_now(self):
        """The picture as it's traced: the one opened, with the parts erased see-through, cropped."""
        img = self.full_img
        if self.erased:
            img = erase(img, self.erased)
        return img if self.crop is None else img.copy(self.crop)

    def _update_picture(self, img):
        """The same picture, changed (erased): traced again, the view as it is."""
        self.img = img
        self.preview = None
        self.left.set_picture(img)
        self.start_trace(auto=False)

    def start_erasing(self, on=True):
        self.set_tool("erase" if on else "select")

    def eraser_size(self, factor):
        self.left.eraser = max(2, min(200, round(self.left.eraser * factor)))
        self.eraser_slider.blockSignals(True)
        self.eraser_slider.setValue(2 * self.left.eraser)
        self.eraser_slider.blockSignals(False)
        self.left.update()

    def on_erased(self, radius, points):
        """A stroke dragged on the picture shown: erase it (in the opened picture's pixels)."""
        if self.full_img is None or not points:
            return
        dx, dy = (self.crop.x(), self.crop.y()) if self.crop is not None else (0, 0)
        stroke = (round(radius, 2), tuple((round(q.x() + dx, 2), round(q.y() + dy, 2)) for q in points))
        self.erased = self.erased + (stroke,)
        self._update_picture(self.picture_now())

    def restore_picture(self):
        """Trace > Restore the picture: nothing erased any more."""
        if not self.erased:
            return
        self.erased = ()
        self._update_picture(self.picture_now())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        local = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        if len(local) > 1 or (local and os.path.isdir(local[0])):
            self.convert_many(local)        # (several pictures, or a folder: to convert them all)
            return
        if local:
            self.open_path(local[0])
            return
        if md.hasImage():
            img = QImage(md.imageData())
            if not img.isNull():
                self.set_image(image.to_rgba(img), None)

    # tracing

    def settings_changed(self):
        self.settings.save(self.qs)
        self._update_tool_bar()
        if self.a_auto.isChecked():
            self.timer.start()

    def auto_changed(self, on):
        self.qs.setValue("trace/auto", int(on))
        if on:
            self.timer.start()

    def auto_settings(self):
        self.start_trace(auto=True)

    def auto_new_changed(self, on):
        self.qs.setValue("trace/auto_new", int(on))

    def start_trace(self, auto=False):
        if self.img is None or self.closing:
            return
        self.timer.stop()
        if self.worker is not None:
            # stop the one running; this one starts when it has
            self.job.cancelled = True
            self.pending = True
            self.pending_auto = self.pending_auto or auto
            return
        auto = auto or self.pending_auto
        self.pending = False
        self.pending_auto = False
        self.job_number += 1
        self.job = Job(self.job_number, self.img, self.settings.options(), self.settings.enlarge_setting(),
                       self.a_colors.isChecked(), auto)
        # a quick preview first when the colors have to be reduced again (a new picture, or another
        # number of colors, smoothing or mode): other settings reuse them and are quick anyway
        o = self.job.options
        colors_key = (id(self.img), o.mode, o.scans, o.smooth)
        self.job.quick = auto or colors_key != self.colors_key
        self.colors_key = colors_key
        self.worker = Worker(self.job)
        self.worker.progress.connect(self.on_progress)
        self.worker.auto_done.connect(self.on_auto_done)
        self.worker.quick_done.connect(self.on_quick_done)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_finished)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText(tr("Picking settings...") if auto else tr("Tracing..."))
        self.worker.start()

    def on_quick_done(self, number, svg):
        if number != self.job_number or self.job.cancelled:
            return
        # shown, not kept: Save and Copy wait for the whole picture's SVG
        self.result = None
        self.right.set_message("")
        self.right.set_svg(svg)
        self.right.title = tr("SVG (quick preview)")
        self.status.setText(tr("Quick preview shown; tracing the whole picture..."))
        self._update_actions()

    def on_auto_done(self, number, options, info):
        if number != self.job_number or self.job.cancelled:
            return
        self.settings.apply_auto(options, self.job.enlarge)
        self.settings.save(self.qs)
        self.status.setText(describe_auto(options, info) + tr(". Tracing..."))

    def on_progress(self, number, f):
        if number == self.job_number:
            self.bar.setValue(int(f * 1000))

    def on_done(self, number, result, preview):
        if number != self.job_number or self.job.cancelled:
            return
        self.result = result
        if preview is not None:
            self.preview = preview
        self.settings.colors.set_palette(result.palette)
        self.right.set_message("")
        self.right.nodes = result.nodes
        self.right.set_svg(result.svg)
        if self.a_colors.isChecked() and self.preview is not None:
            self.left.set_picture(self.preview)
        size = len(result.svg.encode("utf-8"))
        # (the size Save writes: the same bytes)
        self.right.title = tr("SVG: %s, %d shapes, %s nodes") % (_size_text(size), result.shapes,
                                                            i18n.whole(result.nodes))
        self.right.update()
        self._show_saved_size()
        self.remember()
        text = tr("%d shapes, %s nodes, %s, traced in %.2f s") % (result.shapes, i18n.whole(result.nodes),
                                                                  _size_text(size), result.seconds)
        if result.factor != 1:
            text += tr(" (at %d times the size)") % result.factor
        if self.crop is not None:
            text += tr("; cropped to %d x %d pixels") % (self.crop.width(), self.crop.height())
        edited = self.settings.colors.edited_count()
        if edited:
            text += tr("; 1 color edited") if edited == 1 else tr("; %d colors edited") % edited
        if self.job.auto_info is not None:
            text = describe_auto(self.job.options, self.job.auto_info) + ". " + text[0].upper() + text[1:]
        self.status.setText(text)
        self.hover_text = None
        self._update_actions()
        self._update_mark()
        self._update_tool_bar()

    def on_failed(self, number, message):
        if number != self.job_number or not message:
            return
        self.result = None
        self.right.set_svg("")
        self.right.set_message(tr("Couldn't trace the picture:\n%s") % message)
        self.status.setText("")
        self._update_actions()

    def on_finished(self):
        w = self.worker
        self.worker = None
        if w is not None:
            w.deleteLater()
        self.bar.hide()
        if self.pending:
            self.start_trace()

    # View > Language: kept, and used at the next start (every text is made when the window is)

    RESTART = {"en": "KanzonasSVG will be in English the next time it starts.",
               "es": "KanzonasSVG estará en español la próxima vez que se abra."}

    def set_language(self, code):
        self.qs.setValue("view/language", code)
        target = code if code in i18n.LANGUAGES else (i18n.system_language() if i18n.system_language()
                                                       in i18n.LANGUAGES else "en")
        if target != i18n.language():
            QMessageBox.information(self, APP_NAME, self.RESTART[target])

    def show_outlines_changed(self, on):
        """View > Show outlines: the SVG as its outlines, with its nodes (kept for next time)."""
        self.qs.setValue("view/outlines", int(bool(on)))
        self.right.set_outlines(bool(on))

    def show_colors_changed(self, on):
        if self.img is None:
            return
        if on:
            if self.preview is None:
                self.start_trace()
            else:
                self.left.set_picture(self.preview)
        else:
            self.left.set_picture(self.img)
        self.left.title = tr("Colors to trace") if on else tr("Picture")
        self.left.update()
        self.left.update()

    def actual_size(self):
        self.view.scale = 1.0
        self.view.fitted = False
        self.view.changed.emit()

    # saving

    def _show_saved_size(self):
        """Under Saved width: the size the files are saved at."""
        if self.result is None:
            self.settings.size_info.setText("")
            return
        self.settings.picture_px = export.svg_size(self.result.svg)[0]
        self.settings.size_info.setText(tr("Saved at %s") % export.size_text(self.result.svg, self.settings.saved_size()))

    def default_name(self):
        fmt = self.qs.value("paths/format", "svg")
        fmt = fmt if fmt in export.FORMATS else "svg"
        if self.source_path:
            return os.path.splitext(self.source_path)[0] + "." + fmt
        return os.path.join(self.qs.value("paths/save", os.path.expanduser("~")), "picture." + fmt)

    def save(self):
        if self.save_path:
            return self.write(self.save_path)
        return self.save_as()

    def save_as(self, fmt=None):
        """File > Save as SVG/PDF/EPS/DXF...: the file dialog for that kind of file (fmt; None:
        the kind saved last)."""
        if self.result is None:
            return False
        if fmt not in export.FORMATS:
            last = self.qs.value("paths/format", "svg")
            fmt = last if last in export.FORMATS else "svg"
        start = os.path.splitext(self.save_path or self.default_name())[0] + "." + fmt
        path = self.ask_save_path(start, fmt)
        if not path:
            return False
        if os.path.splitext(path)[1].lower().lstrip(".") != fmt:
            path += "." + fmt
        return self.write(path)

    def ask_save_path(self, start, fmt):
        """The file dialog (a test answers it instead)."""
        path, _chosen = QFileDialog.getSaveFileName(self, tr("Save as %s") % fmt.upper(), start,
                                                    export.filter_text(fmt))
        return path

    def write(self, path):
        """Save the trace to path, in the format its extension names (SVG, PDF, EPS or DXF) at
        the saved size. An SVG is written at once; the others in the background (a detailed
        picture's DXF takes a second): wait_saved() waits for them."""
        if self.result is None:
            return False
        fmt = export.format_of(path)
        size = self.settings.saved_size()
        self.save_path = path
        self.qs.setValue("paths/save", os.path.dirname(path))
        self.qs.setValue("paths/format", fmt)
        if fmt == "svg":
            try:
                export.write(path, self.result.svg, fmt, size)
            except OSError as e:
                QMessageBox.warning(self, APP_NAME, tr("Couldn't save %s:\n%s") % (path, e))
                return False
            self.status.setText(tr("Saved %s") % path)
            return True
        t = Saver(path, self.result.svg, fmt, size)
        t.done.connect(self._saved)
        self.savers.append(t)
        self.status.setText(tr("Saving %s...") % path)
        t.start()
        return True

    def _saved(self, saver, error):
        if saver in self.savers:
            self.savers.remove(saver)
        saver.wait()
        if error:
            if not self.closing:
                QMessageBox.warning(self, APP_NAME, tr("Couldn't save %s:\n%s") % (saver.path, error))
        elif not self.closing:
            self.status.setText(tr("Saved %s") % saver.path)

    def wait_saved(self):
        """Wait until every file being saved is written (for quitting, and the tests)."""
        while self.savers:
            t = self.savers[0]
            t.wait()
            QApplication.processEvents()
            if self.savers and self.savers[0] is t:
                self.savers.pop(0)

    def copy_svg(self):
        if self.result is None:
            return
        md = QMimeData()
        svg = export.sized_svg(self.result.svg, self.settings.saved_size())
        data = QByteArray(svg.encode("utf-8"))
        md.setData("image/svg+xml", data)
        md.setData(OURS, b"1")
        md.setText(svg)
        QGuiApplication.clipboard().setMimeData(md)
        _hook_clipboard_release()
        self.status.setText(tr("SVG copied: paste it into Inkscape, Illustrator or another program."))

    # help

    def show_help(self):
        """Help > How to use KanzonasSVG: in chapters, with a search; open beside the window."""
        from kanzonassvg.help_window import HelpWindow
        if self.help is None:
            self.help = HelpWindow(self, help_html(), tr("How to use KanzonasSVG"))
        self.help.show()
        self.help.raise_()
        self.help.activateWindow()
        return self.help

    def about(self):
        try:
            ev = engine.version()
        except engine.TraceError:
            ev = tr("not found")
        logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        head = ("<p><img src='%s' width='468'></p>" % QUrl.fromLocalFile(logo).toString()
                if os.path.exists(logo) else "")
        QMessageBox.about(
            self, tr("About KanzonasSVG"),
            head + "<h3>KanzonasSVG %s</h3>" % __version__
            + "<p>%s</p>" % tr("Turns pictures into SVG files.")
            + "<p>%s</p>" % (tr("Tracing engine %s: Inkscape's Trace Bitmap, with Potrace 1.16 (Peter Selinger) and "
                                "Autotrace 0.40 (Martin Weber and others), with quality and speed fixes. Window: "
                                "Qt for Python (PySide6).") % ev)
            + "<p>%s " % tr("Free software under the GNU General Public License, version 2 or later. Source code:")
            + "<a href='https://github.com/keithlyding/KanzonasSVG'>github.com/keithlyding/KanzonasSVG</a></p>")

    # updates (kanzonassvg/updates.py; the same as KanzonasPDF's)

    def updater(self):
        if getattr(self, "_upd", None) is None:
            from kanzonassvg.updates import UpdateChecker
            self._upd = UpdateChecker(self.qs, self)
            self._upd.found.connect(self._update_found)
            self._upd.result.connect(lambda t: QMessageBox.information(self, tr("Check for updates"), t))
        return self._upd

    def auto_updates_changed(self, on):
        self.updater().set_enabled(on)

    def start_update_check(self):
        """A few seconds after start-up: checks at most once a day, if on. While KanzonasSVG stays
        open, it looks every hour whether a day has passed."""
        if self.closing:
            return
        self.updater().check_if_due()
        if getattr(self, "_update_timer", None) is None:
            self._update_timer = QTimer(self)
            self._update_timer.timeout.connect(lambda: self.updater().check_if_due())
            self._update_timer.start(3600 * 1000)

    def check_updates(self):
        self.statusBar().showMessage(tr("Checking for updates..."), 3000)
        self.updater().check(manual=True)

    def _close_update_bar(self):
        bar = getattr(self, "_update_bar", None)
        if bar is not None:
            self.statusBar().removeWidget(bar)
            bar.deleteLater()
            self._update_bar = None

    def _update_found(self, version):
        if self._upd.manual:
            self.update_box(version)        # asked for: answer in a box
            return
        self._close_update_bar()
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel(tr("<b>KanzonasSVG %s is available</b> (you have %s).") % (version, __version__)))
        buttons = [(tr("What's new"), lambda: self.update_box(version))]
        if self._update_url():
            buttons.append((tr("Update now"), lambda: (self._close_update_bar(), self.update_now())))
        buttons += [(tr("Download"), lambda: (self._close_update_bar(), self._open_release_page())),
                    (tr("Skip this version"), lambda: (self.qs.setValue("updates/skip", version),
                                                       self._close_update_bar())),
                    (tr("Later"), self._close_update_bar)]
        for text, slot in buttons:
            b = QPushButton(text)
            b.clicked.connect(slot)
            h.addWidget(b)
        self._update_bar = bar
        self.statusBar().clearMessage()
        self.statusBar().addWidget(bar)
        bar.show()

    def _open_release_page(self):
        from kanzonassvg import updates
        QDesktopServices.openUrl(QUrl(updates.page(self._upd.release)))

    def _update_url(self):
        """Where the file that updates this copy in place comes from, or None (it can only tell)."""
        from kanzonassvg import updates
        upd = getattr(self, "_upd", None)
        kind = updates.update_kind()
        if upd is None or upd.release is None or kind is None:
            return None
        return updates.asset_url(upd.release, updates.update_file(kind, upd.release))

    def _update_now_text(self):
        from kanzonassvg import updates
        kind = updates.update_kind()
        if kind == "installer":
            return tr("Update now downloads the new setup, checks it, closes KanzonasSVG and installs the "
                      "new version over this one; KanzonasSVG starts again when it's done.")
        if kind == "portable":
            return tr("Update now downloads the new version, checks it, closes KanzonasSVG, puts the new "
                      "program files in this folder and starts it again.")
        if kind == "appimage":
            return tr("Update now downloads the new AppImage, checks it, puts it in place of %s, closes "
                      "KanzonasSVG and starts it again.") % os.path.basename(updates.running_appimage())
        return ""

    def update_box(self, version):
        """The short notes of every version newer than this one, then Update now / Download / Later."""
        from kanzonassvg import updates
        d = QDialog(self)
        d.setWindowTitle(tr("Check for updates"))
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(tr("KanzonasSVG %s is available (you have %s).") % (version, __version__)))
        lay.addWidget(QLabel("<b>%s</b>" % tr("What's new since your version")))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        parts = []
        for v, text, url in updates.notes_since(self._upd.releases):
            parts.append(tr("### Version ") + v)
            parts.append(text or tr("[What's new in %s](%s)") % (v, url))
        notes.setMarkdown("\n\n".join(parts))
        lay.addWidget(notes)
        can = self._update_url() is not None
        info = QLabel(((self._update_now_text() + tr(" Your settings are kept.\n\n")) if can else "")
                      + tr("Download opens the release page in your browser."))
        info.setWordWrap(True)
        lay.addWidget(info)
        box = QDialogButtonBox()
        upd = box.addButton(tr("Update now"), QDialogButtonBox.ButtonRole.AcceptRole) if can else None
        get = box.addButton(tr("Download"), QDialogButtonBox.ButtonRole.AcceptRole)
        box.addButton(tr("Later"), QDialogButtonBox.ButtonRole.RejectRole)
        chosen = []
        box.clicked.connect(lambda b: (chosen.append(b), d.accept()))
        lay.addWidget(box)
        d.resize(600, 520)
        d.exec()
        if chosen and chosen[0] in (upd, get):
            self._close_update_bar()
        if upd is not None and chosen and chosen[0] is upd:
            self.update_now()
        elif chosen and chosen[0] is get:
            self._open_release_page()

    def update_now(self):
        from kanzonassvg import updates
        if updates.downloading():
            QMessageBox.information(self, tr("Update"), tr("The new version is already downloading."))
            return
        url = self._update_url()
        if not url:
            return
        kind = updates.update_kind()
        release = self._upd.release
        name = updates.update_file(kind, release)
        digest = updates.asset_digest(release, name)
        if kind == "appimage":
            target = updates.running_appimage()
            why = updates.appimage_unwritable(target)
            if why:
                QMessageBox.information(self, tr("Update"), tr("KanzonasSVG can't replace %s: %s\n\nThe release page "
                                        "opens so you can download the new %s yourself.") % (target, why, name))
                self._open_release_page()
                return
            dl = updates.AppImageUpdater(url, target, self, expected_sha256=digest)
        elif kind == "installer":
            dl = updates.InstallerUpdater(url, updates.release_version(release), self, expected_sha256=digest)
        else:
            dl = updates.PortableUpdater(url, updates.app_dir(), self, expected_sha256=digest)
        prog = QProgressDialog(tr("Downloading the new KanzonasSVG..."), tr("Cancel"), 0, 0, self)
        prog.setWindowTitle(tr("Update"))
        prog.setMinimumDuration(0)
        prog.canceled.connect(dl.cancel)

        def progress(got, total):
            if total > 0:
                prog.setMaximum(total)
                prog.setValue(got)

        def failed(message):
            prog.close()
            QMessageBox.warning(self, tr("Update"), message + tr("\n\nYou can still download %s from the release "
                                "page.") % name)

        dl.progress.connect(progress)
        dl.failed.connect(failed)
        dl.ready.connect(lambda path: (prog.close(), self._install_update(kind, path)))
        self._download = dl
        dl.start()

    def _install_update(self, kind, path):
        """The checked download is ready: close KanzonasSVG and put it in place."""
        import subprocess
        from kanzonassvg import updates
        if kind == "appimage":
            target = updates.running_appimage()
            # in place first (the running program keeps its own copy open until it ends)
            try:
                updates.replace_appimage(path, target)
            except OSError as e:
                try:
                    os.remove(path)
                except OSError:
                    pass
                QMessageBox.warning(self, tr("Update"), tr("The new version couldn't be put in place of %s (%s). "
                                    "The release page opens so you can download it yourself.") % (target, e))
                self._open_release_page()
                return
            cwd = os.environ.get("OWD") or os.path.expanduser("~")
            self.close()
            subprocess.Popen(updates.restart_command(target), env=updates.restart_env(),
                             cwd=cwd if os.path.isdir(cwd) else None, close_fds=True, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif kind == "installer":
            self.close()
            subprocess.Popen(updates.installer_command(path, updates.app_dir()), close_fds=True)
        else:
            import tempfile
            folder = updates.app_dir()
            # a new folder only this user can write to, not a fixed name another program could
            # put its own script at first
            script = os.path.join(tempfile.mkdtemp(prefix="kzsvgupdate"), "kanzonassvg-update.cmd")
            with open(script, "w", encoding="mbcs" if os.name == "nt" else "utf-8") as f:
                f.write(updates.swap_script(os.getpid(), path, folder))
            self.close()
            subprocess.Popen(["cmd", "/c", script], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             close_fds=True)
        QApplication.quit()

    def closeEvent(self, e):
        self.closing = True
        self.timer.stop()
        self.pending = False
        self.qs.setValue("window/geometry", self.saveGeometry())
        self.settings.save(self.qs)
        if self.worker is not None:
            self.job.cancelled = True
            self.worker.wait()
        for t in list(self.savers):     # (a file being saved is finished first)
            t.wait()
        if self.batch is not None:
            self.batch.close()          # (stops converting: a picture half done isn't saved)
        for t in self.old_loaders + ([self.loader] if self.loader is not None else []):
            t.wait()
        self.left.stop()
        self.right.stop()
        super().closeEvent(e)


def _size_text(n):
    if n < 1024:
        return tr("%d bytes") % n
    if n < 1024 * 1024:
        return "%.0f KB" % (n / 1024)
    return "%.1f MB" % (n / 1024 / 1024)


def run(argv):
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Kanzonas")
    app.setApplicationVersion(__version__)
    i18n.install_qt(app)                # (Qt's own buttons and dialogs in the same language)
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    try:
        engine.library()
    except engine.TraceError as e:
        QMessageBox.critical(None, APP_NAME, str(e))
        return 1
    w = MainWindow()
    w.show()
    QTimer.singleShot(3000, w.start_update_check)
    for a in argv:
        if not a.startswith("-") and os.path.isfile(a):
            w.open_path(a)
            break
    return app.exec()
