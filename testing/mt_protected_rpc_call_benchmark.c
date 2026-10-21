/* This target reuses the validated protected-RPC setup and enables its
 * matched repeated direct/protected call loop.  Keeping the setup in one
 * source prevents the benchmark from drifting from the correctness test. */

#define RPC_BENCHMARK_LOOPS 1
#include "mt_protected_rpc_hardware_test.c"
