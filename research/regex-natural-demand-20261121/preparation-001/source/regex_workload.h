#ifndef REGEX_NATURAL_DEMAND_WORKLOAD_H
#define REGEX_NATURAL_DEMAND_WORKLOAD_H

#include <stddef.h>
#include <stdint.h>

/* Isolated future workload core. No timer, scheduler, CSR, or address hints. */
#define RW_PATTERNS 3u
#define RW_REQUEST_BYTES 4096u
#define RW_MAX_CORPUS_BYTES (128u * 1024u)

typedef struct rw_workload rw_workload;
typedef struct { uint64_t matches, checksum; } rw_result;
typedef struct {
    size_t input_bytes, blocks, corpus_storage_bytes, owned_metadata_bytes;
    /* Excludes opaque libc regex/DFA/allocator state, stack, mappings and code. */
} rw_memory;

enum { RW_OK = 0, RW_ARGUMENT = 1, RW_MEMORY = 2, RW_LIBRARY = 3,
       RW_CORRUPT = 4, RW_POISONED = 5 };

/* *out must be NULL. Init compiles the fixed schema once; all partial failures
 * clean up. Future WHOLE must include create/destroy plus all checks. Locale
 * must already be C; the core refuses others instead of mutating global state. */
int rw_create(rw_workload **out, size_t input_bytes, uint32_t seed);
int rw_request(rw_workload *, rw_result results[RW_PATTERNS]);
/* Independent expected totals derive from block frequencies, not actual sums.
 * Also checks complete corpus integrity. Mandatory before accepting any work. */
int rw_verify(const rw_workload *, uint64_t expected_requests);
void rw_destroy(rw_workload **);
int rw_memory_usage(const rw_workload *, rw_memory *);
const char *rw_pattern(unsigned index);
const char *rw_block(const rw_workload *, size_t index, size_t *length);

#ifdef RW_TESTING
/* Host-only fault injection; production has no configurable patterns/engine. */
void rw_test_reset(void);
void rw_test_fail_allocation(int nth);
void rw_test_fail_compile(int index);
void rw_test_fail_execution(int index);
size_t rw_test_live_owned(void);
unsigned rw_test_compiles(void);
unsigned rw_test_frees(void);
#endif
#endif
