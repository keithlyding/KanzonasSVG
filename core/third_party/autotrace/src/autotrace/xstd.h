/* xstd.h: Wrappers for functions in C standard library
 Was: xmem, xfile */

/* These call the corresponding function in the standard library, and
   abort if those routines fail. */

#ifndef XSTD_H
#define XSTD_H

#include "types.h"
#include <assert.h>
#include <stdlib.h>

/*
 * XMEM
 */
#ifndef __cplusplus
#define XMALLOC(new_mem, size)			\
do						\
  {						\
    assert(size);                               \
    new_mem = (gpointer) malloc (size);	\
    assert(new_mem);				\
  } while (0)

#define XCALLOC(new_mem, size)			\
do						\
  {						\
    assert(size);                               \
    new_mem = (gpointer) calloc (size, 1);	\
    assert(new_mem);				\
  } while (0)

#define XREALLOC(old_ptr, size)				\
do							\
  {							\
    gpointer new_mem;					\
							\
    if (old_ptr == NULL)				\
      XMALLOC (new_mem, size);				\
    else						\
      {							\
        new_mem = (gpointer) realloc (old_ptr, size);	\
        assert(new_mem);				\
      }							\
							\
    old_ptr = new_mem;					\
} while (0)

#else
/* Use templates if Cplusplus... */
#define XMALLOC(new_mem, size)					\
do								\
  {								\
    assert(size);                                               \
    (gpointer&)(new_mem) = (gpointer) malloc (size);	\
     assert(new_mem);						\
  } while (0)

#define XCALLOC(new_mem, sizex)					\
do								\
  {								\
    assert(sizex);                                              \
    (gpointer&)(new_mem) = (void *) calloc (sizex, 1);	\
    assert(new_mem);						\
  } while (0)

#define XREALLOC(old_ptr, size)						  \
do									  \
  {									  \
    gpointer new_mem;							  \
									  \
    if (old_ptr == NULL)						  \
      XMALLOC (new_mem, (size));					  \
    else								  \
      {									  \
        (gpointer&) new_mem = (gpointer) realloc ((old_ptr), (size)); \
        assert(new_mem);						  \
      }									  \
									  \
    (gpointer&)old_ptr = new_mem;					  \
  } while (0)
#endif

/* KanzonasSVG: lists grown one element at a time (append_*) are reallocated only when their
   length reaches a power of two, to twice that, instead of at every element: growing a list of
   n elements took time and memory traffic proportional to n squared (a noisy picture traced in
   many colors makes tens of thousands of outlines; each realloc of a big block is a copy, or a
   new mapping). The allocation of a list of length n is always at least XCAPACITY(n) elements:
   the smallest power of two above n. Lists made all at once (concat) allocate XCAPACITY too. */
#define XCAPACITY(n) at_capacity((size_t)(n))
static inline size_t at_capacity(size_t n)
{
  size_t c = 1;
  while (c <= n)
    c <<= 1;
  return c;
}

#define XGROW(old_ptr, n, elem_size)                               \
do                                                                 \
  {                                                                \
    size_t at_n_ = (size_t)(n);                                    \
    if (at_n_ && (at_n_ & (at_n_ - 1)) == 0)                       \
      XREALLOC (old_ptr, 2 * at_n_ * (elem_size));                 \
  } while (0)

#endif /* Not XSTD_H */
