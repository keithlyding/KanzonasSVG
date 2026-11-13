// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Quantization for Inkscape
 *
 * Authors:
 *   Stéphane Gimenez <dev@gim.name>
 *
 * Copyright (C) 2006 Authors
 *
 * Released under GNU GPL v2+, read the file 'COPYING' for more information.
 */
#include "quantize.h"

#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>

#include "imagemap.h"
#include "pool.h"

namespace Inkscape {
namespace Trace {

namespace {

/**
 * an octree node datastructure
 */
struct Ocnode
{
    Ocnode *parent;           // parent node
    Ocnode **ref;             // node's reference
    Ocnode *child[8];         // children
    int nchild;               // number of children
    int width;                // width level of this node
    RGB rgb;                  // rgb's prefix of that node
    unsigned long weight;     // number of pixels this node accounts for
    unsigned long rs, gs, bs; // sum of pixels colors this node accounts for
    int nleaf;                // number of leaves under this node
    unsigned long mi;         // minimum impact
};

/*
-- algorithm principle:

- inspired by the octree method, we associate a tree to a given color map

- nodes in those trees have this shape:

                                parent
                                   |
        color_prefix(stored in rgb):width
     colors_sum(stored in rs,gs,bs)/weight
         /               |               \
     child1           child2           child3

- (grayscale) trees associated to pixels with colors 87 = 0b1010111 and
  69 = 0b1000101 are:

           .                 .    <-- roots of the trees
           |                 |
    1010111:0  and    1000101:0   <-- color prefixes, written in binary form
         87/1              69/1   <-- color sums, written in decimal form

- the result of merging the two trees is:

                   .
                   |
                 10:5       <----- longest common prefix and binary width
                156/2       <---.  of the covered color range.
            /            \      |
    1000101:0      1010111:0    '- sum of colors and quantity of pixels
         69/1           87/1       this node accounts for

  one should consider three cases when two trees are to be merged:
  - one tree range is included in the range of the other one, and the first
    tree has to be inserted as a child (or merged with the corresponding
    child) of the other.
  - their ranges are the same, and their children have to be merged under
    a single root.
  - ranges have no intersection, and a fork node has to be created (like in
    the given example).

- a tree for an image is built dividing the image in 2 parts and merging
  the trees obtained recursively for the two parts. a tree for a one pixel
  part is a leaf like one of those which were given above.

- last, this tree is reduced a specified number of leaves, deleting first
  leaves with minimal impact i.e. [ weight * 2^(2*parentwidth) ] value :
  a fair approximation of the impact a leaf removal would have on the final
  result : it's the corresponding covered area times the square of the
  introduced color distance.

  deletion of a node A below a node with only two children is done as
  follows :

  - when the sibling is a leaf, the sibling is deleted as well, both nodes
    are then represented by their parent.

     |               |
     .       ==>     .
    / \
   A   .

  - otherwise the deletion of A deletes also its parent, which plays no
    role anymore:

     |                |
     .       ==>       \
    / \                 |
   A   .                .
      / \              / \

  in that way, every leaf removal operation really decreases the remaining
  total number of leaves by one.

- very last, color indexes are attributed to leaves; associated colors are
  averages, computed from weight and color components sums.

-- improvements to the usual octree method:

- since this algorithm shall often be used to perform quantization using a
  very low (2-16) set of colors and not with a usual 256 value, we choose
  more carefully which nodes are to be deleted.

- depth of leaves is not fixed to an arbitrary number (which should be 8
  when color components are in 0-255), so there is no need to go down to a
  depth of 8 for each pixel (at full precision), unless it is really
  required.

- tree merging also fastens the overall tree building, and intermediate
  processing could be done.

- a huge optimization against the stupid removal algorithm (i.e. find a best
  match over the whole tree, remove it and do it again) was implemented:
  nodes are marked with the minimal impact of the removal of a leaf below
  it. we proceed to the removal recursively. we stop when current removal
  level is above the current node minimal, otherwise reached leaves are
  removed, and every change over minimal impacts is propagated back to the
  whole tree when the recursion ends.

-- specific optimizations

- pool allocation is used to allocate nodes (increased performance on large
  images).

*/

RGB operator>>(RGB rgb, int s)
{
    RGB res;
    res.r = rgb.r >> s;
    res.g = rgb.g >> s;
    res.b = rgb.b >> s;
    return res;
}

bool operator==(RGB rgb1, RGB rgb2)
{
    return rgb1.r == rgb2.r && rgb1.g == rgb2.g && rgb1.b == rgb2.b;
}

int childIndex(RGB rgb)
{
    return ((rgb.r & 1) << 2) | ((rgb.g & 1) << 1) | (rgb.b & 1);
}

/**
 * allocate a new node
 */
Ocnode *ocnodeNew(Pool<Ocnode> &pool)
{
    Ocnode *node = pool.draw();
    node->ref = nullptr;
    node->parent = nullptr;
    node->nchild = 0;
    for (auto &i : node->child) {
        i = nullptr;
    }
    node->mi = 0;
    return node;
}

void ocnodeFree(Pool<Ocnode> &pool, Ocnode *node)
{
    pool.drop(node);
}

/**
 * free a full octree
 */
void octreeDelete(Pool<Ocnode> &pool, Ocnode *node)
{
    if (!node) return;
    for (auto &i : node->child) {
        octreeDelete(pool, i);
    }
    ocnodeFree(pool, node);
}

/**
 *  pretty-print an octree, debugging purposes
 */
#if 0
void ocnodePrint(Ocnode *node, int indent)
{
    if (!node) return;
    printf("width:%d weight:%lu rgb:%6x nleaf:%d mi:%lu\n",
           node->width,
           node->weight,
           (unsigned int)(
           ((node->rs / node->weight) << 16) +
           ((node->gs / node->weight) << 8) +
           (node->bs / node->weight)),
           node->nleaf,
           node->mi
           );
    for (int i = 0; i < 8; i++) if (node->child[i])
        {
        for (int k = 0; k < indent; k++) printf(" ");//indentation
        printf("[%d:%p] ", i, node->child[i]);
        ocnodePrint(node->child[i], indent+2);
        }
}

void octreePrint(Ocnode *node)
{
    printf("<<octree>>\n");
    if (node) printf("[r:%p] ", node); ocnodePrint(node, 2);
}
#endif

/**
 *  merge nodes <node1> and <node2> at location <ref> with parent <parent>
 */
int octreeMerge(Pool<Ocnode> &pool, Ocnode *parent, Ocnode **ref, Ocnode *node1, Ocnode *node2)
{
    assert(ref);
    if (!node1 && !node2) return 0;
    assert(node1 != node2);
    if (parent && !*ref) parent->nchild++;
    if (!node1) {
        *ref = node2; node2->ref = ref; node2->parent = parent;
        return node2->nleaf;
    }
    if (!node2) {
        *ref = node1; node1->ref = ref; node1->parent = parent;
        return node1->nleaf;
    }
    int dwitdth = node1->width - node2->width;
    if (dwitdth > 0 && node1->rgb == node2->rgb >> dwitdth) {
        // place node2 below node1
        *ref = node1; node1->ref = ref; node1->parent = parent;
        int i = childIndex(node2->rgb >> (dwitdth - 1));
        node1->rs += node2->rs; node1->gs += node2->gs; node1->bs += node2->bs;
        node1->weight += node2->weight;
        node1->mi = 0;
        if (node1->child[i]) node1->nleaf -= node1->child[i]->nleaf;
        node1->nleaf += octreeMerge(pool, node1, &node1->child[i], node1->child[i], node2);
        return node1->nleaf;
    } else if (dwitdth < 0 && node2->rgb == node1->rgb >> (-dwitdth)) {
        // place node1 below node2
        *ref = node2; node2->ref = ref; node2->parent = parent;
        int i = childIndex(node1->rgb >> (-dwitdth - 1));
        node2->rs += node1->rs; node2->gs += node1->gs; node2->bs += node1->bs;
        node2->weight += node1->weight;
        node2->mi = 0;
        if (node2->child[i]) node2->nleaf -= node2->child[i]->nleaf;
        node2->nleaf += octreeMerge(pool, node2, &node2->child[i], node2->child[i], node1);
        return node2->nleaf;
    } else {
        // nodes have either no intersection or the same root
        Ocnode *newnode;
        newnode = ocnodeNew(pool);
        newnode->rs = node1->rs + node2->rs;
        newnode->gs = node1->gs + node2->gs;
        newnode->bs = node1->bs + node2->bs;
        newnode->weight = node1->weight + node2->weight;
        *ref = newnode; newnode->ref = ref; newnode->parent = parent;
        if (dwitdth == 0 && node1->rgb == node2->rgb) {
            // merge the nodes in <newnode>
            newnode->width = node1->width; // == node2->width
            newnode->rgb = node1->rgb;     // == node2->rgb
            newnode->nchild = 0;
            newnode->nleaf = 0;
            if (node1->nchild == 0 && node2->nchild == 0) {
                newnode->nleaf = 1;
            } else {
                for (int i = 0; i < 8; i++) {
                    if (node1->child[i] || node2->child[i]) {
                        newnode->nleaf += octreeMerge(pool, newnode, &newnode->child[i], node1->child[i], node2->child[i]);
                    }
                }
            }
            ocnodeFree(pool, node1); ocnodeFree(pool, node2);
            return newnode->nleaf;
        } else {
            // use <newnode> as a fork node with children <node1> and <node2>
            int newwidth = std::max(node1->width, node2->width);
            RGB rgb1 = node1->rgb >> (newwidth - node1->width);
            RGB rgb2 = node2->rgb >> (newwidth - node2->width);
            // according to the previous tests <rgb1> != <rgb2> before the loop
            while (!(rgb1 == rgb2)) {
                rgb1 = rgb1 >> 1;
                rgb2 = rgb2 >> 1;
                newwidth++;
            }
            newnode->width = newwidth;
            newnode->rgb = rgb1; // == rgb2
            newnode->nchild = 2;
            newnode->nleaf = node1->nleaf + node2->nleaf;
            int i1 = childIndex(node1->rgb >> (newwidth - node1->width - 1));
            int i2 = childIndex(node2->rgb >> (newwidth - node2->width - 1));
            node1->parent = newnode;
            node1->ref = &newnode->child[i1];
            newnode->child[i1] = node1;
            node2->parent = newnode;
            node2->ref = &newnode->child[i2];
            newnode->child[i2] = node2;
            return newnode->nleaf;
        }
    }
}

/**
 * upatade mi value for leaves
 */
void ocnodeMi(Ocnode *node)
{
    node->mi = node->parent ? node->weight << (2 * node->parent->width) : 0;
}

/**
 * remove leaves whose prune impact value is lower than <lvl>. at most
 * <count> leaves are removed, and <count> is decreased on each removal.
 * all parameters including minimal impact values are regenerated.
 */
void ocnodeStrip(Pool<Ocnode> &pool, Ocnode **ref, int &count, unsigned long lvl)
{
    Ocnode *node = *ref;
    if (!node) return;
    assert(ref == node->ref);
    if (node->nchild == 0) { // leaf node
        if (!node->mi) ocnodeMi(node); // mi generation may be required
        if (node->mi > lvl) return; // leaf is above strip level
        ocnodeFree(pool, node);
        *ref = nullptr;
        count--;
    } else {
        if (node->mi && node->mi > lvl) return; // node is above strip level
        node->nchild = 0;
        node->nleaf = 0;
        node->mi = 0;
        Ocnode **lonelychild = nullptr;
        for (auto & i : node->child) {
            if (i) {
                ocnodeStrip(pool, &i, count, lvl);
                if (i) {
                    lonelychild = &i;
                    node->nchild++;
                    node->nleaf += i->nleaf;
                    if (!node->mi || node->mi > i->mi) {
                        node->mi = i->mi;
                    }
                }
            }
        }
        // tree adjustments
        if (node->nchild == 0) {
            count++;
            node->nleaf = 1;
            ocnodeMi(node);
        } else if (node->nchild == 1) {
            if ((*lonelychild)->nchild == 0) {
                // remove the <lonelychild> leaf under a 1 child node
                node->nchild = 0;
                node->nleaf = 1;
                ocnodeMi(node);
                ocnodeFree(pool, *lonelychild);
                *lonelychild = nullptr;
            } else {
                // make a bridge to <lonelychild> over a 1 child node
                (*lonelychild)->parent = node->parent;
                (*lonelychild)->ref = ref;
                ocnodeFree(pool, node);
                *ref = *lonelychild;
            }
        }
    }
}

/**
 * reduce the leaves of an octree to a given number
 */
void octreePrune(Pool<Ocnode> &pool, Ocnode **ref, int ncolor)
{
    assert(ref);
    assert(ncolor > 0);
    int n = (*ref)->nleaf - ncolor;
    if (!*ref || n <= 0) return;
    while (n > 0) {
        ocnodeStrip(pool, ref, n, (*ref)->mi);
    }
}

/**
 * build an octree from the leaves <leaves>[first, last) by merging halves,
 * which keeps the merges balanced.
 */
void octreeBuildLeaves(Pool<Ocnode> &pool, std::vector<Ocnode *> const &leaves, Ocnode **ref, size_t first, size_t last)
{
    if (last - first == 1) {
        *ref = leaves[first];
        (*ref)->ref = ref;
        return;
    }
    size_t mid = first + (last - first) / 2;
    Ocnode *ref1 = nullptr;
    Ocnode *ref2 = nullptr;
    octreeBuildLeaves(pool, leaves, &ref1, first, mid);
    octreeBuildLeaves(pool, leaves, &ref2, mid, last);
    octreeMerge(pool, nullptr, ref, ref1, ref2);
}

/**
 * build an octree associated to the <rgbmap> color map,
 * pruned to <ncolor> colors.
 *
 * Pixels are first counted into a histogram of colors cut to their top
 * HIST_BITS bits per channel, keeping the exact color sums of each bin, and
 * the tree is built from one weighted leaf per used bin rather than one leaf
 * per pixel: a few hundred thousand leaves at most instead of one per pixel
 * (12 million for a 4000x3000 image). The palette is made of at most 256
 * colors, so pruning would merge colors this close anyway, and as the sums
 * are exact, each palette color is still the exact mean of its pixels.
 */
Ocnode *octreeBuild(Pool<Ocnode> &pool, RgbMap const &rgbmap, int ncolor)
{
    constexpr int HIST_BITS = 6;
    constexpr int SHIFT = 8 - HIST_BITS;

    struct Bin
    {
        unsigned long weight = 0;
        unsigned long rs = 0, gs = 0, bs = 0;
    };
    std::vector<Bin> bins(1u << (3 * HIST_BITS));

    for (auto const &px : rgbmap.pixels) {
        auto &bin = bins[((px.r >> SHIFT) << (2 * HIST_BITS)) | ((px.g >> SHIFT) << HIST_BITS) | (px.b >> SHIFT)];
        bin.weight++;
        bin.rs += px.r;
        bin.gs += px.g;
        bin.bs += px.b;
    }

    std::vector<Ocnode *> leaves;
    for (unsigned key = 0; key < bins.size(); key++) {
        auto const &bin = bins[key];
        if (!bin.weight) {
            continue;
        }
        Ocnode *node = ocnodeNew(pool);
        node->width = SHIFT;
        node->rgb.r = key >> (2 * HIST_BITS);
        node->rgb.g = (key >> HIST_BITS) & ((1u << HIST_BITS) - 1);
        node->rgb.b = key & ((1u << HIST_BITS) - 1);
        node->rs = bin.rs;
        node->gs = bin.gs;
        node->bs = bin.bs;
        node->weight = bin.weight;
        node->nleaf = 1;
        node->mi = 0;
        leaves.push_back(node);
    }

    Ocnode *node = nullptr;
    if (!leaves.empty()) {
        octreeBuildLeaves(pool, leaves, &node, 0, leaves.size());
    }

    // prune the octree
    if (node) {
        octreePrune(pool, &node, ncolor);
    }

    return node;
}

/**
 * compute the color palette associated to an octree, with the weight of each color.
 */
void octreeIndex(Ocnode *node, RGB *rgbpal, unsigned long *weights, int &index)
{
    if (!node) return;
    if (node->nchild == 0) {
        // Round to the nearest value: truncating darkened every color by up to one step.
        rgbpal[index].r = (node->rs + node->weight / 2) / node->weight;
        rgbpal[index].g = (node->gs + node->weight / 2) / node->weight;
        rgbpal[index].b = (node->bs + node->weight / 2) / node->weight;
        weights[index] = node->weight;
        index++;
    } else {
        for (auto &i : node->child) {
            if (i) {
                octreeIndex(i, rgbpal, weights, index);
            }
        }
    }
}

/**
 * Merge palette colors that can't be told apart (closest pair first, weighted mean)
 * and return the new number of colors. When an image has fewer colors than asked
 * for, the spare ones split a color into near-identical twins (JPEG noise in a flat
 * area), and the border between twins is noise: thousands of nodes for nothing.
 */
int mergeCloseColors(RGB *rgbs, unsigned long *weights, int n)
{
    constexpr int CLOSE = 3 * 10 * 10; // about 10 levels per channel
    auto dist2 = [](RGB a, RGB b) {
        return (a.r - b.r) * (a.r - b.r) + (a.g - b.g) * (a.g - b.g) + (a.b - b.b) * (a.b - b.b);
    };
    while (n > 1) {
        int bi = -1, bj = -1, bd = CLOSE + 1;
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                int d = dist2(rgbs[i], rgbs[j]);
                if (d < bd) {
                    bd = d;
                    bi = i;
                    bj = j;
                }
            }
        }
        if (bi < 0) {
            break;
        }
        unsigned long wi = weights[bi], wj = weights[bj], w = std::max(wi + wj, 1ul);
        rgbs[bi].r = (rgbs[bi].r * wi + rgbs[bj].r * wj + w / 2) / w;
        rgbs[bi].g = (rgbs[bi].g * wi + rgbs[bj].g * wj + w / 2) / w;
        rgbs[bi].b = (rgbs[bi].b * wi + rgbs[bj].b * wj + w / 2) / w;
        weights[bi] = wi + wj;
        rgbs[bj] = rgbs[n - 1];
        weights[bj] = weights[n - 1];
        n--;
    }
    return n;
}

/**
 * compute the squared distance between two colors
 */
int distRGB(RGB rgb1, RGB rgb2)
{
    return (rgb1.r - rgb2.r) * (rgb1.r - rgb2.r)
         + (rgb1.g - rgb2.g) * (rgb1.g - rgb2.g)
         + (rgb1.b - rgb2.b) * (rgb1.b - rgb2.b);
}

/**
 * find the index of closest color in a palette
 */
int findRGB(RGB const *rgbs, int ncolor, RGB rgb)
{
    int index = -1, dist = 0;
    for (int k = 0; k < ncolor; k++) {
        int d = distRGB(rgbs[k], rgb);
        if (index == -1 || d < dist) { dist = d; index = k; }
    }
    return index;
}

} // namespace

/**
 * quantize an RGB image to a reduced number of colors.
 */
IndexedMap rgbMapQuantize(RgbMap const &rgbmap, int ncolor)
{
    assert(ncolor > 0);

    auto imap = IndexedMap(rgbmap.width, rgbmap.height);

    Pool<Ocnode> pool;
    auto tree = octreeBuild(pool, rgbmap, ncolor);

    auto rgbs = std::make_unique<RGB[]>(ncolor);
    auto counts = std::make_unique<unsigned long[]>(ncolor);
    int index = 0;
    octreeIndex(tree, rgbs.get(), counts.get(), index);

    octreeDelete(pool, tree);

    index = mergeCloseColors(rgbs.get(), counts.get(), index);

    // The image may have fewer colors than asked for: only the first <index>
    // entries are filled in. Sorting or searching the unfilled ones (black)
    // used to give pixels the index of a color that was never traced, so
    // such images came out partly or entirely empty.
    int const nused = index;

    // stacking with increasing contrasts
    std::sort(rgbs.get(), rgbs.get() + nused,
              [](auto &ra, auto &rb) { return (ra.r + ra.g + ra.b) < (rb.r + rb.g + rb.b); });

    // make the new map
    // fill in the color lookup table
    for (int i = 0; i < nused; i++) {
        imap.clut[i] = rgbs[i];
    }
    imap.nrColors = nused;

    if (nused == 0) {
        return imap;
    }

    // fill in new map pixels
    if (nused < 255 && rgbmap.pixels.size() > (1u << 20)) {
        // On big images, remember the nearest palette color of each color met
        // (255 = not computed yet) instead of searching the palette per pixel.
        std::vector<unsigned char> nearest(1u << 24, 255);
        auto out = imap.pixels.begin();
        for (auto const &rgb : rgbmap.pixels) {
            auto &n = nearest[(rgb.r << 16) | (rgb.g << 8) | rgb.b];
            if (n == 255) {
                n = findRGB(rgbs.get(), nused, rgb);
            }
            *out++ = n;
        }
    } else {
        for (size_t i = 0; i < rgbmap.pixels.size(); i++) {
            imap.pixels[i] = findRGB(rgbs.get(), nused, rgbmap.pixels[i]);
        }
    }

    return imap;
}

/**
 * Merge palette colors that ended up nearly the same (about 10 levels per channel): each
 * one's pixels go to the one with more pixels. Returns how many were merged.
 *
 * The palette is picked on the smoothed picture, where a hard edge between two colors that
 * aren't far apart comes out softened: the pixels next to it, a few levels off, can get a
 * palette color of their own, and once refinePalette() has set each color from the original
 * picture, two of them can be the same color give or take a level or two (a clean picture of
 * 3 colors traced with Smooth on gave 6 layers, two of them copies).
 */
int mergeDuplicateColors(IndexedMap &imap)
{
    int n = imap.nrColors;
    if (n < 2) {
        return 0;
    }
    constexpr int CLOSE = 3 * 10 * 10;
    std::vector<size_t> count(n, 0);
    for (auto k : imap.pixels) {
        if ((int)k < n) {
            count[k]++;
        }
    }
    std::vector<int> target(n);
    for (int k = 0; k < n; k++) {
        target[k] = k;
    }
    auto dist2 = [](RGB a, RGB b) {
        return (a.r - b.r) * (a.r - b.r) + (a.g - b.g) * (a.g - b.g) + (a.b - b.b) * (a.b - b.b);
    };
    int merged = 0;
    while (true) {
        int bi = -1, bj = -1, bd = CLOSE + 1;
        for (int i = 0; i < n; i++) {
            if (target[i] != i) {
                continue;
            }
            for (int j = i + 1; j < n; j++) {
                if (target[j] != j) {
                    continue;
                }
                int d = dist2(imap.clut[i], imap.clut[j]);
                if (d < bd) {
                    bd = d;
                    bi = i;
                    bj = j;
                }
            }
        }
        if (bi < 0) {
            break;
        }
        int keep = count[bi] >= count[bj] ? bi : bj, gone = keep == bi ? bj : bi;
        for (int k = 0; k < n; k++) {
            if (target[k] == gone) {
                target[k] = keep;
            }
        }
        count[keep] += count[gone];
        merged++;
    }
    if (!merged) {
        return 0;
    }
    // compact the palette, keeping its order (stacking goes by it)
    std::vector<int> newIndex(n, -1);
    int m = 0;
    for (int k = 0; k < n; k++) {
        if (target[k] == k) {
            imap.clut[m] = imap.clut[k];
            newIndex[k] = m++;
        }
    }
    for (auto &k : imap.pixels) {
        if ((int)k < n) {
            k = newIndex[target[k]];
        }
    }
    imap.nrColors = m;
    return merged;
}

/**
 * Set each palette color to the color of <original> over the pixels of that color whose
 * eight neighbors have it too (over all its pixels if it has no such pixel): the color
 * that most of those pixels have exactly, when one does (a flat color), else their mean.
 *
 * The palette is chosen on the smoothed image, where the pixels next to an edge are
 * slightly mixed with their soft (anti-aliased) edge: a logo's colors came out a step
 * or two off. The insides of its shapes have the exact colors. Their mean alone was
 * still a step off where soft edges are wider than a pixel (a picture enlarged before
 * tracing): the lighter or darker pixels next to the edge count as inside too.
 */
void refinePalette(RgbMap const &original, IndexedMap &imap)
{
    int const width = imap.width;
    int const height = imap.height;
    int const n = imap.nrColors;
    if (n == 0 || original.width != width || original.height != height) {
        return;
    }

    struct Sum
    {
        unsigned long long r = 0, g = 0, b = 0, count = 0;
        void add(RGB c)
        {
            r += c.r;
            g += c.g;
            b += c.b;
            count++;
        }
    };
    auto pack = [](RGB c) { return (unsigned)c.r << 16 | (unsigned)c.g << 8 | c.b; };
    auto is_interior = [&](int x, int y, unsigned k) {
        if (x == 0 || y == 0 || x + 1 == width || y + 1 == height) {
            return false;
        }
        for (int dy = -1; dy <= 1; dy++) {
            auto row = imap.pixels.data() + (size_t)(y + dy) * width;
            if (row[x - 1] != k || row[x] != k || row[x + 1] != k) {
                return false;
            }
        }
        return true;
    };

    // Means, and the candidate for the majority color of each (Boyer-Moore vote).
    std::vector<Sum> inner(n), all(n);
    std::vector<unsigned> candidate(n, 0), votes(n, 0);
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            size_t i = (size_t)y * width + x;
            unsigned k = imap.pixels[i];
            auto c = original.pixels[i];
            all[k].add(c);
            if (is_interior(x, y, k)) {
                inner[k].add(c);
                unsigned v = pack(c);
                if (votes[k] == 0) {
                    candidate[k] = v;
                    votes[k] = 1;
                } else {
                    votes[k] += candidate[k] == v ? 1 : -1;
                }
            }
        }
    }

    // Is the candidate really over half of them?
    std::vector<unsigned long long> exact(n, 0);
    for (int y = 1; y + 1 < height; y++) {
        for (int x = 1; x + 1 < width; x++) {
            size_t i = (size_t)y * width + x;
            unsigned k = imap.pixels[i];
            if (votes[k] && pack(original.pixels[i]) == candidate[k] && is_interior(x, y, k)) {
                exact[k]++;
            }
        }
    }

    for (int k = 0; k < n; k++) {
        if (inner[k].count && exact[k] * 2 > inner[k].count) {
            unsigned v = candidate[k];
            imap.clut[k] = {(unsigned char)(v >> 16), (unsigned char)(v >> 8 & 255), (unsigned char)(v & 255)};
            continue;
        }
        auto const &s = inner[k].count ? inner[k] : all[k];
        if (s.count) {
            imap.clut[k] = {(unsigned char)((s.r + s.count / 2) / s.count),
                            (unsigned char)((s.g + s.count / 2) / s.count),
                            (unsigned char)((s.b + s.count / 2) / s.count)};
        }
    }
}

/**
 * Drop the palette colors that only exist as rims between two other colors.
 *
 * Asked for more colors than a logo has, the palette fills up with the mixes found
 * on its anti-aliased edges: a blue logo on white traced with 8 scans got 6 shades
 * of light blue, each traced as a thin ring around every shape, which looks blurry
 * and multiplies the nodes. A palette color is dropped when it lies between two
 * other palette colors (a mix of them), most of its pixels touch another color (it
 * only forms thin rims), and it has at most a quarter of the pixels of either of the
 * two; its pixels go to the nearer of the two. Colors that
 * fill areas of their own are kept, even if they are a mix of two others.
 */
void dropBlendColors(RgbMap const &rgbmap, IndexedMap &imap)
{
    int const n = imap.nrColors;
    int const width = imap.width;
    int const height = imap.height;
    if (n < 3 || width < 3 || height < 3) {
        return;
    }

    // Pixels of each color, and how many of them touch another color.
    std::vector<size_t> total(n), onEdge(n);
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            size_t i = (size_t)y * width + x;
            unsigned k = imap.pixels[i];
            total[k]++;
            if ((x > 0 && imap.pixels[i - 1] != k) || (x + 1 < width && imap.pixels[i + 1] != k) ||
                (y > 0 && imap.pixels[i - width] != k) || (y + 1 < height && imap.pixels[i + width] != k)) {
                onEdge[k]++;
            }
        }
    }
    auto thin = [&](int k) { return total[k] > 0 && onEdge[k] * 2 > total[k]; };

    // For each thin color, the pair of colors filling areas of their own that it mixes.
    auto const &pal = imap.clut;
    std::vector<int> endA(n, -1), endB(n, -1);
    bool any = false;
    for (int c = 0; c < n; c++) {
        if (!thin(c)) {
            continue;
        }
        double best = -1;
        for (int a = 0; a < n; a++) {
            for (int b = a + 1; b < n; b++) {
                if (a == c || b == c || thin(a) || thin(b)) {
                    continue;
                }
                double abr = pal[b].r - pal[a].r, abg = pal[b].g - pal[a].g, abb = pal[b].b - pal[a].b;
                double len2 = abr * abr + abg * abg + abb * abb;
                if (len2 == 0) {
                    continue;
                }
                double t =
                    ((pal[c].r - pal[a].r) * abr + (pal[c].g - pal[a].g) * abg + (pal[c].b - pal[a].b) * abb) / len2;
                if (t <= 0.02 || t >= 0.98) {
                    continue;
                }
                double er = pal[c].r - (pal[a].r + t * abr), eg = pal[c].g - (pal[a].g + t * abg),
                       eb = pal[c].b - (pal[a].b + t * abb);
                double e = er * er + eg * eg + eb * eb;
                // Within a tenth of the two colors' distance from the line between them.
                // A rim is much smaller than the two areas it lies between; colors
                // in a painting or photo are of like sizes and are kept.
                bool const rim = total[c] * 4 <= std::min(total[a], total[b]);
                if (rim && e * 100 <= len2 && (best < 0 || e < best)) {
                    best = e;
                    endA[c] = a;
                    endB[c] = b;
                }
            }
        }
        any = any || endA[c] >= 0;
    }
    if (!any) {
        return;
    }

    // Give the pixels of dropped colors to the nearer end, by their own color.
    for (size_t i = 0; i < imap.pixels.size(); i++) {
        unsigned k = imap.pixels[i];
        if (endA[k] < 0) {
            continue;
        }
        RGB A = pal[endA[k]], B = pal[endB[k]], c = rgbmap.pixels[i];
        double abr = B.r - A.r, abg = B.g - A.g, abb = B.b - A.b;
        double t = ((c.r - A.r) * abr + (c.g - A.g) * abg + (c.b - A.b) * abb) / (abr * abr + abg * abg + abb * abb);
        imap.pixels[i] = t < 0.5 ? endA[k] : endB[k];
    }

    // Close the gaps in the palette, keeping its order.
    std::vector<unsigned> renumber(n);
    int kept = 0;
    for (int k = 0; k < n; k++) {
        if (endA[k] < 0) {
            imap.clut[kept] = imap.clut[k];
            renumber[k] = kept++;
        }
    }
    for (auto &k : imap.pixels) {
        k = renumber[k];
    }
    imap.nrColors = kept;
}

/**
 * Give anti-aliased edge pixels to one of the two colors they blend.
 *
 * Where two flat colors meet, the edge pixels are a mix of the two (anti-aliasing,
 * scanning, JPEG). Mapped to the nearest palette color, such a pixel often goes to a
 * third color that happens to be closer, which drew a thin rim of an unrelated color
 * around shapes (a gray or blue outline around red letters, for example) and added a
 * path for every rim. Here an edge pixel that sits far from its own palette color is
 * looked at against the colors of the pixels around it that match their palette color
 * well: if it is closer to a mix of two of those than to its own color, it goes to the
 * nearer of the two. <rgbmap> is the image that was quantized, <imap> its quantized map.
 */
void snapBlendedEdges(RgbMap const &rgbmap, IndexedMap &imap)
{
    int const width = imap.width;
    int const height = imap.height;
    if (width < 3 || height < 3 || imap.nrColors < 2) {
        return;
    }

    auto const &pal = imap.clut;
    auto dist2 = [](int r, int g, int b, RGB p) {
        return (r - p.r) * (r - p.r) + (g - p.g) * (g - p.g) + (b - p.b) * (b - p.b);
    };

    // A pixel within this squared distance of its palette color matches it ("sure"):
    // about 16 levels per channel, above JPEG and scanner noise in flat areas.
    constexpr int SURE = 3 * 16 * 16;
    std::vector<unsigned char> sure(imap.pixels.size());
    for (size_t i = 0; i < sure.size(); i++) {
        auto c = rgbmap.pixels[i];
        sure[i] = dist2(c.r, c.g, c.b, pal[imap.pixels[i]]) <= SURE;
    }

    auto out = imap.pixels;
    constexpr int R = 2; // look this far around a pixel for the colors it may blend
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            size_t i = (size_t)y * width + x;
            if (sure[i]) {
                continue;
            }
            unsigned own = imap.pixels[i];

            // Only edge pixels: some neighbor has another color.
            bool edge = false;
            for (int dy = -1; dy <= 1 && !edge; dy++) {
                for (int dx = -1; dx <= 1; dx++) {
                    int xx = x + dx, yy = y + dy;
                    if (xx >= 0 && yy >= 0 && xx < width && yy < height &&
                        imap.pixels[(size_t)yy * width + xx] != own) {
                        edge = true;
                        break;
                    }
                }
            }
            if (!edge) {
                continue;
            }

            // The colors of the sure pixels around it (few: an edge meets 2 or 3).
            unsigned cand[8];
            int ncand = 0;
            for (int yy = std::max(0, y - R); yy <= std::min(height - 1, y + R); yy++) {
                for (int xx = std::max(0, x - R); xx <= std::min(width - 1, x + R); xx++) {
                    size_t j = (size_t)yy * width + xx;
                    if (!sure[j]) {
                        continue;
                    }
                    unsigned k = imap.pixels[j];
                    bool seen = false;
                    for (int n = 0; n < ncand; n++) {
                        seen = seen || cand[n] == k;
                    }
                    if (!seen && ncand < 8) {
                        cand[ncand++] = k;
                    }
                }
            }
            if (ncand < 2) {
                continue;
            }

            auto c = rgbmap.pixels[i];
            double best = dist2(c.r, c.g, c.b, pal[own]);
            int choice = -1;
            for (int a = 0; a < ncand; a++) {
                for (int b = a + 1; b < ncand; b++) {
                    RGB A = pal[cand[a]], B = pal[cand[b]];
                    double abr = B.r - A.r, abg = B.g - A.g, abb = B.b - A.b;
                    double len2 = abr * abr + abg * abg + abb * abb;
                    if (len2 == 0) {
                        continue;
                    }
                    double t = ((c.r - A.r) * abr + (c.g - A.g) * abg + (c.b - A.b) * abb) / len2;
                    t = std::clamp(t, 0.0, 1.0);
                    double er = c.r - (A.r + t * abr), eg = c.g - (A.g + t * abg), eb = c.b - (A.b + t * abb);
                    double e = er * er + eg * eg + eb * eb;
                    if (e < best) {
                        best = e;
                        choice = t < 0.5 ? cand[a] : cand[b];
                    }
                }
            }
            if (choice >= 0) {
                out[i] = choice;
            }
        }
    }

    imap.pixels = std::move(out);
}

} // namespace Trace
} // namespace Inkscape
