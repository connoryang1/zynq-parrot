/**
 * mt_ctxtsw_microbench.c
 *
 * Stripped-down context switch microbenchmark.
 *
 * Purpose:
 *   Measure the raw T0->T1->T0 round-trip latency with as little benchmark
 *   overhead as possible:
 *   - no loop-carried printing
 *   - no worker-side C code
 *   - only a bare T1 asm stub that switches back to T0 once
 *
 * This is not a replacement for mt_benchmark.c. It is a narrower diagnostic
 * test for the Banyan-style 7-cycle single-switch target.
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512
static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn)) t1_ping(void);

static inline void write_ctxt(uint64_t v) {
  __asm__ volatile("csrw 0x800, %0" : : "r"(v));
}

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x801, %0" : : "r"(v));
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x802, %0" : : "r"(v));
}

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, cycle" : "=r"(v));
  return v;
}

static inline void restore_gp(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la gp, __global_pointer$\n"
    ".option pop\n"
    :
    :
    : "gp"
  );
}

static inline uint64_t round_trip_once(uint64_t tid) {
  uint64_t before = read_cycle();
  write_ctxt(tid);
  return read_cycle() - before;
}

static inline void seed_thread(uint64_t tid, uint64_t *stack_top) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, (uint64_t)t1_ping);
}

/* Thread 1 immediately switches back to T0, then parks forever if execution
 * ever falls through instead of being redirected away by the context switch. */
void __attribute__((naked, noinline, noreturn)) t1_ping(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la   gp, __global_pointer$\n"
    ".option pop\n"
    "li   t0, 0\n"
    "csrw 0x800, t0\n"
    "1:\n"
    "j    1b\n"
  );
}

int main(void) {
  /* Keep the measurement path simple and avoid reseeding the same live thread.
   * Use threads 1, 2, and 3 exactly once each. */
  uint64_t cold, warm0, warm1;

  seed_thread(1, &t1_stack[STACK_WORDS]);
  cold = round_trip_once(1);

  seed_thread(2, &t2_stack[STACK_WORDS]);
  warm0 = round_trip_once(2);

  seed_thread(3, &t3_stack[STACK_WORDS]);
  warm1 = round_trip_once(3);

  uint64_t warm_min = warm0;
  if (warm1 < warm_min)
    warm_min = warm1;

  restore_gp();
  bp_print_string("=== Context Switch Microbenchmark ===\n");
  bp_print_string("Target: ~7 cycles per switch, ~14 cycles round-trip\n");
  bp_print_string("Method: fixed-count T0->T1->T0 measurements, no per-trial loop output\n\n");

  restore_gp();
  bp_print_string("Cold round-trip: ");
  bp_hprint_uint64(cold);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm round-trip 0: ");
  bp_hprint_uint64(warm0);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm round-trip 1: ");
  bp_hprint_uint64(warm1);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm min round-trip: ");
  bp_hprint_uint64(warm_min);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm min single-switch estimate: ");
  bp_hprint_uint64(warm_min / 2);
  bp_print_string(" cycles\n");

  bp_finish(0);
  return 0;
}
