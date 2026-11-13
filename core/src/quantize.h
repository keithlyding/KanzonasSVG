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

#include <cstdint>
#include <vector>

#include "imagemap.h"

namespace Inkscape {
namespace Trace {

/**
 * How many pixels of each color an image has (6 bits a channel), with their sums: what the
 * quantizer's octree is built from, the same for any number of colors (kept between traces).
 */
struct ColorHistogram
{
    static constexpr int BITS = 6;
    struct Bin
    {
        uint64_t weight = 0;
        uint64_t rs = 0, gs = 0, bs = 0;
    };
    std::vector<Bin> bins;
};

ColorHistogram colorHistogram(RgbMap const &rgbmap);

/**
 * Quantize an RGB image to a reduced number of colors (with its histogram, if already made).
 */
IndexedMap rgbMapQuantize(RgbMap const &rgbmap, int nrColors, ColorHistogram const *histogram = nullptr);

/**
 * Set each palette color to the mean of <original> over the insides of its areas.
 */
void refinePalette(RgbMap const &original, IndexedMap &imap);

/**
 * Merge palette colors that ended up nearly the same; returns how many were merged.
 */
int mergeDuplicateColors(IndexedMap &imap);

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
