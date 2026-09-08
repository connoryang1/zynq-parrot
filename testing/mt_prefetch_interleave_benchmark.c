/* Run the independent-request comparison using real nonfaulting prefetch.r.
 * Share the exact request streams, checksums, control and timing boundaries
 * with the faulting-load variant. A transaction trace, not this PASS alone,
 * establishes whether prefetches or backing-memory requests overlapped.
 */
#define BP_REQUEST_PREFETCH_R 1
#include "mt_request_interleave_benchmark.c"
