// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Some filters for Potrace in Inkscape
 *
 * Authors:
 *   Bob Jamison <rjamison@titan.com>
 *   Stéphane Gimenez <dev@gim.name>
 *
 * Copyright (C) 2004-2006 Authors
 *
 * Released under GNU GPL v2+, read the file 'COPYING' for more information.
 */
#ifndef INKSCAPE_TRACE_FILTERSET_H
#define INKSCAPE_TRACE_FILTERSET_H

#include "imagemap.h"

namespace Inkscape {
namespace Trace {

/**
 * Apply gaussian blur to an GrayMap.
 */
GrayMap grayMapGaussian(GrayMap const &gmap);

/**
 * Edge-preserving smoothing of an RGB map: a 5x5 Gaussian over the neighbors
 * whose color is close to the pixel's own, so edges stay sharp.
 */
RgbMap rgbMapGaussian(RgbMap const &rgbmap);

GrayMap grayMapCanny(GrayMap const &gmap, double lowThreshold, double highThreshold);

GrayMap quantizeBand(RgbMap const &rgbmap, int nrColors);

} // namespace Trace
} // namespace Inkscape

#endif // INKSCAPE_TRACE_FILTERSET_H
