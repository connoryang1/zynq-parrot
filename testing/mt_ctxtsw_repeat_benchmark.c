/**
 * mt_ctxtsw_repeat_benchmark.c
 *
 * Repeated warm-path context-switch benchmark.
 *
 * Purpose:
 *   Quantify how often the minimal T0->T1->T0 round-trip actually stays at the
 *   7-cycle-per-switch target once the fast path has been reached.
 *
 * Method:
 *   - Seed T1 once for the cold round-trip
 *   - Reseed the inactive T1 context before each warm round-trip
 *   - Count how many trials hit the ideal 14-cycle round-trip exactly
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512
#define N_TRIALS    64
#define IDEAL_RT    14ULL

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
  uint64_t warm_min = ~0ULL;
  uint64_t warm_max = 0;
  uint64_t warm_total = 0;
  uint64_t exact_14 = 0;
  uint64_t exact_15 = 0;
  uint64_t gt_14 = 0;

  seed_thread(1, &t1_stack[STACK_WORDS]);
  cold = round_trip_once();

  for (uint64_t i = 0; i < N_TRIALS; i++) {
    seed_thread(1, &t1_stack[STACK_WORDS]);
    uint64_t elapsed = round_trip_once();
    warm_total += elapsed;
    if (elapsed < warm_min)
      warm_min = elapsed;
    if (elapsed > warm_max)
      warm_max = elapsed;
    if (elapsed == 14)
      exact_14++;
    if (elapsed == 15)
      exact_15++;
    if (elapsed > 14)
      gt_14++;
  }

  restore_gp();
  bp_print_string("=== Repeated Warm Context Switch Benchmark ===\n");
  bp_print_string("Goal: quantify how often the warm path stays at 14-cycle round-trip\n");
  bp_print_string("Trials: ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n\n");

  restore_gp();
  bp_print_string("Cold round-trip:       ");
  bp_hprint_uint64(cold);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm min round-trip:   ");
  bp_hprint_uint64(warm_min);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm max round-trip:   ");
  bp_hprint_uint64(warm_max);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Warm avg round-trip:   ");
  bp_hprint_uint64(warm_total / N_TRIALS);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Exact 14-cycle trials: ");
  bp_hprint_uint64(exact_14);
  bp_print_string(" / ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n");

  restore_gp();
  bp_print_string("Exact 15-cycle trials: ");
  bp_hprint_uint64(exact_15);
  bp_print_string(" / ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n");

  restore_gp();
  bp_print_string(">14-cycle trials:      ");
  bp_hprint_uint64(gt_14);
  bp_print_string(" / ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n");

  restore_gp();
  bp_print_string("Warm min single-switch:");
  bp_print_string(" ");
  bp_hprint_uint64(warm_min / 2);
  bp_print_string(" cycles\n");

  bp_finish(0);
  return 0;
}
