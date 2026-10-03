/* Repeatedly exercise the physical Linux probe's prefetch/switch/load shape.
 * Each epoch displaces the target arrays, reseeds the resident peer, and runs
 * 256 requests per context.  Architectural checks establish liveness and
 * register preservation; a trace is required to measure detached-buffer and
 * UCE occupancy at each epoch boundary.
 */
#include <stdint.h>
#include "bp_prefetch.h"
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 10
#error "Lifecycle test requires two resident banks and ten logical contexts"
#endif

#define EPOCHS 6
#define LINES 256
#define LINE_BYTES 64
#define EVICTION_LINES 1024
#define PEER_DONE UINT64_C(0x50415353)

static volatile unsigned char source_data[LINES * LINE_BYTES]
  __attribute__((aligned(4096), used));
static volatile unsigned char peer_data[LINES * LINE_BYTES]
  __attribute__((aligned(4096), used));
static volatile unsigned char eviction[EVICTION_LINES * LINE_BYTES]
  __attribute__((aligned(4096), used));
static volatile uint64_t expected_address[2] __attribute__((aligned(64), used));
static volatile uint64_t observed_address[2] __attribute__((aligned(64), used));
static volatile uint64_t mismatch_iteration[2] __attribute__((aligned(64), used));
static volatile uint64_t peer_done, eviction_sink;

#define WORKER_BODY(id, target, base, after_return, mismatch, done) \
  ".option push\n.option norvc\n" \
  "la a0, " base "\nli a2, 256\n" \
  "la a4, expected_address\nla a5, observed_address\n" \
  "la a6, mismatch_iteration\naddi a4, a4, " #id "*8\n" \
  "addi a5, a5, " #id "*8\naddi a6, a6, " #id "*8\n" \
  "1: addi t3, a2, -1\nslli t0, t3, 6\nadd t0, a0, t0\n" \
  "sd t0, 0(a4)\n" BP_PREFETCH_R_ASM("t0") \
  "csrw 0x800, " #target "\n" after_return \
  "ld t1, 0(a4)\nbeq t0, t1, 2f\nsd t0, 0(a5)\nsd a2, 0(a6)\n" \
  mismatch \
  "2: ld t2, 0(t0)\naddi a2, a2, -1\nbnez a2, 1b\n" done \
  ".option pop\n"

static __attribute__((naked, noinline, noreturn, used, aligned(64)))
void peer(void)
{
  __asm__ volatile(WORKER_BODY(1, 0, "peer_data", "",
    "fence rw,rw\ncsrwi 0x800, 0\n3: j 3b\n",
    "la t0, peer_done\nli t1, 0x50415353\nsd t1, 0(t0)\n"
    "fence rw,rw\ncsrwi 0x800, 0\n3: j 3b\n"));
}

static __attribute__((naked, noinline, used, aligned(64)))
void source(void)
{
  __asm__ volatile(WORKER_BODY(0, 1, "source_data",
    "la t4, mismatch_iteration\nld t4, 8(t4)\nbnez t4, 8f\n",
    "ret\n", "8: ret\n"));
}

static void fail(void)
{
  bp_print_string("[BSG-FAIL] repeated prefetch handoff lifecycle\n");
  bp_finish(1);
}

int main(void)
{
  for (unsigned epoch = 0; epoch < EPOCHS; ++epoch) {
    uint64_t displaced = 0;
    for (unsigned i = 0; i < EVICTION_LINES; ++i)
      displaced += eviction[i * LINE_BYTES];
    eviction_sink = displaced;
    __asm__ volatile("fence rw, rw" : : : "memory");

    peer_done = 0;
    expected_address[0] = expected_address[1] = 0;
    observed_address[0] = observed_address[1] = 0;
    mismatch_iteration[0] = mismatch_iteration[1] = 0;
    seed_npc(1, (uint64_t)peer);
    source();
    if (!mismatch_iteration[0] && !mismatch_iteration[1])
      __asm__ volatile("csrwi 0x800, 1" : : : "memory");
    if (peer_done != PEER_DONE || mismatch_iteration[0]
        || mismatch_iteration[1])
      fail();
    bp_print_string("PREFETCH-HANDOFF-LIFECYCLE epoch-pass=");
    bp_hprint_uint64(epoch + 1);
    bp_print_string("\n");
  }

  bp_print_string("[BSG-PASS] repeated prefetch handoff lifecycle\n");
  bp_finish(0);
  return 0;
}
