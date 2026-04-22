/**
 * mt_ctxtsw_partial_unroll_benchmark.c
 *
 * Purpose:
 *   Measure steady-state ctxtsw cost in a ring of contexts while reducing the
 *   per-switch loop bookkeeping that inflates a naive switch-only loop.
 *
 * Why this exists:
 *   A simple ring benchmark of
 *     csrw 0x081, next
 *     addi loop_counter, -1
 *     bnez loop
 *   measures the switch plus two extra retired instructions per iteration.
 *   That shape reported 9 cycles/switch on this repo.
 *
 *   This benchmark keeps the same seeded-thread / resumed-loop control flow,
 *   but partially unrolls the switch body so the addi+bnez pair is amortized
 *   across multiple switches. That gives a cleaner steady-state estimate of
 *   switch cost without jumping to a fully unrolled stress pattern.
 */

#include <stdint.h>
#include "bp_utils.h"

#define NUM_CONTEXTS 4
#define SWITCHES_PER_CONTEXT 256
#define UNROLL_FACTOR 4
#define LOOP_ITERS (SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x082, %0" : : "r"(v));
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x083, %0" : : "r"(v));
}

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static inline void seed_thread(uint64_t tid, uint64_t *stack_top, uint64_t entry) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, entry);
}

void __attribute__((noinline, noreturn)) t1_ring(void) {
  for (uint64_t i = 0; i < LOOP_ITERS; i++) {
    __asm__ volatile(
      "csrwi 0x081, 2\n"
      "csrwi 0x081, 2\n"
      "csrwi 0x081, 2\n"
      "csrwi 0x081, 2\n"
    );
  }

  for (;;)
    ;
}

void __attribute__((noinline, noreturn)) t2_ring(void) {
  for (uint64_t i = 0; i < LOOP_ITERS; i++) {
    __asm__ volatile(
      "csrwi 0x081, 3\n"
      "csrwi 0x081, 3\n"
      "csrwi 0x081, 3\n"
      "csrwi 0x081, 3\n"
    );
  }

  for (;;)
    ;
}

void __attribute__((noinline, noreturn)) t3_ring(void) {
  for (uint64_t i = 0; i < LOOP_ITERS; i++) {
    __asm__ volatile(
      "csrwi 0x081, 0\n"
      "csrwi 0x081, 0\n"
      "csrwi 0x081, 0\n"
      "csrwi 0x081, 0\n"
    );
  }

  for (;;)
    ;
}

int main(void) {
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  uint64_t begin = read_cycle();
  for (uint64_t i = 0; i < LOOP_ITERS; i++) {
    __asm__ volatile(
      "csrwi 0x081, 1\n"
      "csrwi 0x081, 1\n"
      "csrwi 0x081, 1\n"
      "csrwi 0x081, 1\n"
    );
  }
  uint64_t end = read_cycle();

  uint64_t diff = end - begin;
  uint64_t num_switches = NUM_CONTEXTS * SWITCHES_PER_CONTEXT;
  uint64_t cycles_per_switch = diff / num_switches;

  bp_print_string("=== Partial-Unroll Switch Benchmark ===\n");
  bp_print_string("Loop bookkeeping amortized across multiple switches\n");
  bp_print_string("Contexts:             ");
  bp_hprint_uint64(NUM_CONTEXTS);
  bp_print_string("\n");
  bp_print_string("Switches/context:     ");
  bp_hprint_uint64(SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Unroll factor:        ");
  bp_hprint_uint64(UNROLL_FACTOR);
  bp_print_string("\n");
  bp_print_string("Total cycles:         ");
  bp_hprint_uint64(diff);
  bp_print_string("\n");
  bp_print_string("Cycles per switch:    ");
  bp_hprint_uint64(cycles_per_switch);
  bp_print_string("\n");

  bp_finish(0);
  return 0;
}
