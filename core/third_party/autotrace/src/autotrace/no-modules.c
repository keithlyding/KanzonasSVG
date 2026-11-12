/* SPDX-License-Identifier: GPL-2.0-or-later
 *
 * KanzonasSVG builds Autotrace without its input and output modules (it hands
 * Autotrace a bitmap in memory and reads the splines back): nothing to set up.
 */
#include "private.h"

int at_input_init(void) { return 0; }
int at_output_init(void) { return 0; }
int at_module_init(void) { return 0; }
