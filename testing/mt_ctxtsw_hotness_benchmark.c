/**
 * mt_ctxtsw_hotness_benchmark.c
 *
 * Same-entry cold-vs-hot context-switch benchmark.
 *
 * Purpose:
 *   Measure whether the minimal T0->T1->T0 path stays at 14 cycles when the
 *   resumed-thread entry point is held constant and only its I$ hotness changes.
 *
 * Method:
 *   - Cold measurement: seed T1 once and measure the first touch of the worker
 *   - Hot measurement: seed T1, do one untimed warm-up switch, reseed the same
 *     exact worker PC, then measure the same entry point while warm
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512
#define N_TRIALS    16

static uint64_t t1_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn)) t1_ping(void);

static inline void write_ctxt_1(void) {
  __asm__ volatile("csrwi 0x081, 1");
}

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

static inline void seed_thread(uint64_t tid, uint64_t *stack_top) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, (uint64_t)t1_ping);
}

static inline uint64_t round_trip_once(void) {
  uint64_t before = read_cycle();
  write_ctxt_1();
  return read_cycle() - before;
}

void __attribute__((naked, noinline, noreturn)) t1_ping(void) {
  __asm__ volatile(
    "csrwi 0x081, 0\n"
    "1:\n"
    "j    1b\n"
  );
}

int main(void) {
  uint64_t cold;
  uint64_t hot_min = ~0ULL;
  uint64_t hot_max = 0;
  uint64_t hot_total = 0;
  uint64_t exact_14 = 0;

  seed_thread(1, &t1_stack[STACK_WORDS]);
  cold = round_trip_once();

  for (uint64_t i = 0; i < N_TRIALS; i++) {
    seed_thread(1, &t1_stack[STACK_WORDS]);
    (void)round_trip_once();

    seed_thread(1, &t1_stack[STACK_WORDS]);
    uint64_t elapsed = round_trip_once();
    hot_total += elapsed;
    if (elapsed < hot_min)
      hot_min = elapsed;
    if (elapsed > hot_max)
      hot_max = elapsed;
    if (elapsed == 14)
      exact_14++;
  }

  restore_gp();
  bp_print_string("=== Same-Entry Hotness Context Switch Benchmark ===\n");
  bp_print_string("Goal: separate same-PC I$ hotness from broader FE disturbance.\n");
  bp_print_string("Trials: ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n\n");

  restore_gp();
  bp_print_string("Cold first-touch:      ");
  bp_hprint_uint64(cold);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Hot min round-trip:    ");
  bp_hprint_uint64(hot_min);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Hot max round-trip:    ");
  bp_hprint_uint64(hot_max);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Hot avg round-trip:    ");
  bp_hprint_uint64(hot_total / N_TRIALS);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Exact 14-cycle trials: ");
  bp_hprint_uint64(exact_14);
  bp_print_string(" / ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n");

  restore_gp();
  bp_print_string("Hot min single-switch: ");
  bp_hprint_uint64(hot_min / 2);
  bp_print_string(" cycles\n");

  bp_finish(0);
  return 0;
}
