// SPDX-License-Identifier: GPL-2.0-or-later
/*
 *  Quantization for Inkscape
 *
 * Authors:
 *   Stéphane Gimenez <dev@gim.name>
 *
 * Copyright (C) 2006 Authors
 *
 * Released under GNU GPL v2+, read the file 'COPYING' for more information.
 */
#ifndef INKSCAPE_TRACE_QUANTIZE_H
#define INKSCAPE_TRACE_QUANTIZE_H

#include "imagemap.h"

namespace Inkscape {
namespace Trace {

/**
 * Quantize an RGB image to a reduced number of colors.
 */
IndexedMap rgbMapQuantize(RgbMap const &rgbmap, int nrColors);

/**
 * Set each palette color to the mean of <original> over the insides of its areas.
 */
void refinePalette(RgbMap const &original, IndexedMap &imap);

/**
 * Drop the palette colors that only exist as rims between two other colors.
 */
void dropBlendColors(RgbMap const &rgbmap, IndexedMap &imap);

/**
 * Give anti-aliased edge pixels to one of the two colors they blend.
 */
void snapBlendedEdges(RgbMap const &rgbmap, IndexedMap &imap);

} // namespace Trace
} // namespace Inkscape

#endif // INKSCAPE_TRACE_QUANTIZE_H
