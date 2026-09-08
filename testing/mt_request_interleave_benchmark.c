/* Measure two resident workers issuing their own independent memory requests.
 * Compare prefetch/yield/consume with a no-prefetch handoff control and batch2.
 * Inputs are shuffled, first-touch cache lines; a trace establishes admission
 * overlap. This small mechanism test is separate from the Linux-thread baseline.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_load_ahead.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Independent-request test requires two resident banks/four logical contexts"
#endif

#define LINES 64
#define MODES 3
#define SAMPLES 3
struct cache_line { uint64_t value, padding[7]; };
#define LINE(n) { (n) + 1, {0} }
#define BLOCK16(n) LINE(n), LINE(n+1), LINE(n+2), LINE(n+3), \
  LINE(n+4), LINE(n+5), LINE(n+6), LINE(n+7), LINE(n+8), LINE(n+9), \
  LINE(n+10), LINE(n+11), LINE(n+12), LINE(n+13), LINE(n+14), LINE(n+15)
#define DATA { BLOCK16(0), BLOCK16(16), BLOCK16(32), BLOCK16(48) }
#define SAMPLE { DATA, DATA, DATA }
/* NBF initializes memory without warming the target cache. Sample0 warms code
 * and control; samples1..3 use disjoint pages, one per mode. No guest setup or
 * verification reads a measured line before its run. No downstream cold-state
 * guarantee is implied. These replicas intentionally use identical values/order.
 */
static const volatile struct cache_line request_data[SAMPLES + 1][MODES][LINES]
  __attribute__((aligned(4096), used)) = { SAMPLE, SAMPLE, SAMPLE, SAMPLE };

/* Fixed permutation of 0..63 (Python Random(42).shuffle). Even/odd positions
 * belong to workers0/1, respectively. No thread sees its peer's request list.
 * This small hot index table avoids PRNG computation in the measured loop.
 */
static const uint16_t request_order[LINES] __attribute__((aligned(64), used)) = {
  23, 25, 7, 22, 45, 33, 19, 59, 46, 9, 40, 18, 42, 31, 16, 21,
  36, 41, 29, 20, 11, 50, 39, 48, 3, 30, 24, 55, 4, 57, 54, 49,
  10, 0, 60, 28, 44, 26, 52, 12, 35, 53, 38, 32, 58, 13, 51, 62,
  2, 27, 37, 5, 34, 56, 43, 6, 61, 8, 63, 15, 17, 47, 1, 14
};
struct result {
  uint64_t sum[2], count[2], peer_id, done, cycles;
};
static volatile struct result trial_result __attribute__((aligned(64), used));

/* All state uses caller-saved integer registers. Each worker prepares one
 * request, optionally starts its load, yields, and consumes only on resumption.
 * It cannot prepare its next address until the previous load has been summed.
 * Only loop/address/checksum work is present: no latency-padding arithmetic.
 */
#define PREPARE "lhu t1, 0(a1)\nslli t1, t1, 6\nadd t2, a0, t1\n"
#define CONSUME "ld t4, 0(t2)\nadd t0, t0, t4\n"
#define ADVANCE "addi a1, a1, 4\naddi a2, a2, -1\nbnez a2, 1b\n"
#define SOURCE_BEGIN \
  ".option push\n.option norvc\nli t0, 0\nli t6, 0\nfence rw, rw\n" \
  "csrr t3, 0xcc0\n1:\n"
#define SOURCE_END \
  "addi t6, t6, 1\n" ADVANCE \
  /* Drain the final pending peer load before stopping the common counter. */ \
  "csrwi 0x800, 1\ncsrr t5, 0xcc0\nsub t5, t5, t3\n" \
  "fence rw, rw\nsd t0, 0(a3)\nsd t6, 16(a3)\nsd t5, 48(a3)\n" \
  "ret\n.option pop\n"

static __attribute__((naked, noinline, aligned(64)))
void resident_control(const volatile struct cache_line *data,
                      const uint16_t *order, uint64_t pairs,
                      volatile struct result *out)
{
  __asm__ volatile(SOURCE_BEGIN PREPARE "csrwi 0x800, 1\n" CONSUME SOURCE_END);
}

static __attribute__((naked, noinline, aligned(64)))
void resident_ahead(const volatile struct cache_line *data,
                    const uint16_t *order, uint64_t pairs,
                    volatile struct result *out)
{
  __asm__ volatile(SOURCE_BEGIN PREPARE
    ".global request_source_prefetch\nrequest_source_prefetch:\n"
    BP_LOAD_AHEAD_ASM("t2") "csrwi 0x800, 1\n" CONSUME SOURCE_END);
}

#define PEER_BEGIN \
  ".option push\n.option norvc\nli t0, 0\nli t6, 0\n1:\n"
#define PEER_END \
  "csrwi 0x800, 0\n" CONSUME "addi t6, t6, 1\n" ADVANCE \
  "sd t0, 8(a3)\nsd t6, 24(a3)\n" \
  "csrr t1, 0x800\nsd t1, 32(a3)\nli t1, 1\nsd t1, 40(a3)\n" \
  "csrwi 0x800, 0\n2: j 2b\n.option pop\n"

static __attribute__((naked, noinline, noreturn, aligned(64)))
void control_peer(void)
{
  __asm__ volatile(PEER_BEGIN PREPARE PEER_END);
}

static __attribute__((naked, noinline, noreturn, aligned(64)))
void ahead_peer(void)
{
  __asm__ volatile(PEER_BEGIN PREPARE
    ".global request_peer_prefetch\nrequest_peer_prefetch:\n"
    BP_LOAD_AHEAD_ASM("t2") PEER_END);
}

/* The batched schedule alone may see both request streams. Prepare the two
 * addresses, issue both load-ahead operations, then consume both useful loads.
 * lbu x0 is a faulting ordinary load in every ahead mode, not an ISA hint.
 */
static __attribute__((naked, noinline, aligned(64)))
void batch_two(const volatile struct cache_line *data,
               const uint16_t *order, uint64_t pairs,
               volatile struct result *out)
{
  __asm__ volatile(
    ".option push\n.option norvc\nli t0, 0\nli t6, 0\n"
    "li a4, 0\nfence rw, rw\ncsrr t3, 0xcc0\n1:\n"
    PREPARE "lhu t4, 2(a1)\nslli t4, t4, 6\nadd t5, a0, t4\n"
    BP_LOAD_AHEAD_ASM("t2") BP_LOAD_AHEAD_ASM("t5")
    "ld t4, 0(t2)\nadd t0, t0, t4\nld t4, 0(t5)\nadd t6, t6, t4\n"
    "addi a4, a4, 1\n" ADVANCE
    "csrr t5, 0xcc0\nsub t5, t5, t3\nfence rw, rw\n"
    "sd t0, 0(a3)\nsd t6, 8(a3)\nsd a4, 16(a3)\nsd a4, 24(a3)\nsd t5, 48(a3)\n"
    "ret\n.option pop\n");
}

static void fail(void)
{
  bp_print_string("[BSG-FAIL] independent-request data/count/context mismatch\n");
  bp_finish(1);
}

int main(void)
{
  uint64_t expected[2] = {0, 0}, seen = 0;
  uint64_t cycles[SAMPLES][MODES];
  for (unsigned i = 0; i < LINES; ++i) {
    if (request_order[i] >= LINES || (seen & (1ULL << request_order[i])))
      fail();
    seen |= 1ULL << request_order[i];
    expected[i & 1] += request_order[i] + 1;
  }
  for (unsigned sample = 0; sample <= SAMPLES; ++sample) {
    for (unsigned position = 0; position < MODES; ++position) {
      const unsigned mode = (position + sample) % MODES;
      const volatile struct cache_line *data = request_data[sample][mode];
      trial_result = (struct result){0};
      if (mode == 1) {
        batch_two(data, request_order, LINES / 2, &trial_result);
      } else {
        /* Peers are leaf assembly, needing neither stack nor gp. Reseeding
         * happens only after the previous trial has completed and suspended.
         */
        seed_reg(1, 10, (uint64_t)data);
        seed_reg(1, 11, (uint64_t)&request_order[1]);
        seed_reg(1, 12, LINES / 2);
        seed_reg(1, 13, (uint64_t)&trial_result);
        seed_npc(1, (uint64_t)(mode == 0 ? control_peer : ahead_peer));
        if (mode == 0)
          resident_control(data, request_order, LINES / 2, &trial_result);
        else
          resident_ahead(data, request_order, LINES / 2, &trial_result);
        if (trial_result.count[1] != LINES / 2 || trial_result.peer_id != 1
            || trial_result.done != 1)
          fail();
      }
      uint64_t current;
      __asm__ volatile("csrr %0, 0x800" : "=r"(current) : : "memory");
      if (current != 0 || trial_result.sum[0] != expected[0]
          || trial_result.sum[1] != expected[1] || !trial_result.cycles
          || trial_result.count[0] != LINES / 2 || trial_result.count[1] != LINES / 2)
        fail();
      if (sample)
        cycles[sample - 1][mode] = trial_result.cycles;
    }
  }
  bp_print_string("Benchmark: two independent resident request streams\n");
  bp_print_string("64 loads/sample; cold shuffled lines; faulting lbu x0\n");
  bp_print_string("Hex cycles: resident control / batch2 / resident ahead\n");
  for (unsigned sample = 0; sample < SAMPLES; ++sample) {
    for (unsigned mode = 0; mode < MODES; ++mode) {
      bp_hprint_uint64(cycles[sample][mode]);
      bp_print_string(mode == MODES - 1 ? "\n" : " / ");
    }
  }
  bp_print_string("[BSG-PASS] independent requests\n");
  bp_finish(0);
  return 0;
}
