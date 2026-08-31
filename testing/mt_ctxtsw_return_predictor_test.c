/**
 * mt_ctxtsw_return_predictor_test.c
 *
 * Characterizes call/return predictor behavior across context switches. The
 * current FE has per-thread BTB/BHT instances, while RAS/global history need
 * explicit measurement. This benchmark reports pre/post return-chain timing
 * around a T1 return-path pollution phase.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define WARMUP_REPS 4
#define MEASURE_REPS 8
#define POLLUTE_REPS 64

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t sink = 0;

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static inline void write_ctxt(uint64_t v) {
  __asm__ volatile("csrw 0x800, %0" : : "r"(v) : "memory");
}

static __attribute__((noinline)) uint64_t leaf8(uint64_t x) { return x + 0x8; }
static __attribute__((noinline)) uint64_t leaf7(uint64_t x) { return leaf8(x) + 0x7; }
static __attribute__((noinline)) uint64_t leaf6(uint64_t x) { return leaf7(x) + 0x6; }
static __attribute__((noinline)) uint64_t leaf5(uint64_t x) { return leaf6(x) + 0x5; }
static __attribute__((noinline)) uint64_t leaf4(uint64_t x) { return leaf5(x) + 0x4; }
static __attribute__((noinline)) uint64_t leaf3(uint64_t x) { return leaf4(x) + 0x3; }
static __attribute__((noinline)) uint64_t leaf2(uint64_t x) { return leaf3(x) + 0x2; }
static __attribute__((noinline)) uint64_t leaf1(uint64_t x) { return leaf2(x) + 0x1; }

static __attribute__((noinline)) uint64_t time_return_chain(uint64_t reps) {
  uint64_t start = read_cycle();
  uint64_t acc = sink;
  for (uint64_t i = 0; i < reps; i++)
    acc += leaf1(i);
  sink = acc;
  return read_cycle() - start;
}

void __attribute__((noinline, noreturn)) t1_pollute_returns(void) {
  for (uint64_t i = 0; i < POLLUTE_REPS; i++)
    sink += leaf1(i ^ 0x55);
  write_ctxt(0);
  while (1) { }
}

int main(void) {
  bp_print_string("=== Ctxtsw Return Predictor Benchmark ===\n");

  for (uint64_t i = 0; i < WARMUP_REPS; i++)
    time_return_chain(32);

  uint64_t pre_min = ~0ULL;
  for (uint64_t i = 0; i < MEASURE_REPS; i++) {
    uint64_t t = time_return_chain(32);
    if (t < pre_min) pre_min = t;
  }

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_pollute_returns);
  write_ctxt(1);

  uint64_t post_min = ~0ULL;
  for (uint64_t i = 0; i < MEASURE_REPS; i++) {
    uint64_t t = time_return_chain(32);
    if (t < post_min) post_min = t;
  }

  bp_print_string("Pre-switch return-chain min cycles:  ");
  bp_hprint_uint64(pre_min);
  bp_print_string("\n");
  bp_print_string("Post-switch return-chain min cycles: ");
  bp_hprint_uint64(post_min);
  bp_print_string("\n");
  bp_print_string("Absolute delta:                      ");
  bp_hprint_uint64((post_min > pre_min) ? (post_min - pre_min) : (pre_min - post_min));
  bp_print_string("\n");
  bp_print_string("[BSG-PASS] return predictor benchmark complete\n");
  bp_finish(0);
  return 0;
}
