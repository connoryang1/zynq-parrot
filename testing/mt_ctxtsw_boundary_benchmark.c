/**
 * mt_ctxtsw_boundary_benchmark.c
 *
 * Context-switch benchmark with rotating worker entry points.
 *
 * Purpose:
 *   Stress the resumed-thread fetch path more than the pure hot-path microbench
 *   by rotating T1 across several separate stub entry points. This is not a
 *   workload benchmark; it is a narrow "less ideal FE locality" benchmark.
 *
 * Method:
 *   - T0 reseeds inactive T1 before each trial
 *   - T1 resumes at one of four separate stub addresses
 *   - each stub immediately switches back to T0
 *   - trial-by-trial latency shows whether the 14-cycle round-trip survives
 *     mild I$ footprint disturbance
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512
#define N_TRIALS    8

static uint64_t t1_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ping_a(void);
void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ping_b(void);
void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ping_c(void);
void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ping_d(void);

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

static inline void seed_thread(uint64_t tid, uint64_t *stack_top, uint64_t npc) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, npc);
}

static inline uint64_t round_trip_once(void) {
  uint64_t before = read_cycle();
  write_ctxt_1();
  return read_cycle() - before;
}

#define DEFINE_T1_STUB(name)                  \
  void __attribute__((naked, noinline, noreturn, aligned(64))) name(void) { \
    __asm__ volatile(                        \
      "csrwi 0x081, 0\n"                     \
      "1:\n"                                 \
      "j    1b\n"                            \
    );                                       \
  }

DEFINE_T1_STUB(t1_ping_a)
DEFINE_T1_STUB(t1_ping_b)
DEFINE_T1_STUB(t1_ping_c)
DEFINE_T1_STUB(t1_ping_d)

int main(void) {
  uint64_t npcs[4] = {
    (uint64_t)t1_ping_a,
    (uint64_t)t1_ping_b,
    (uint64_t)t1_ping_c,
    (uint64_t)t1_ping_d,
  };
  uint64_t min_cycles = ~0ULL;
  uint64_t max_cycles = 0;
  uint64_t total_cycles = 0;
  uint64_t exact_14 = 0;
  uint64_t first_pass[4] = {0, 0, 0, 0};

  restore_gp();
  bp_print_string("=== Rotating Entry Context Switch Benchmark ===\n");
  bp_print_string("Goal: see whether 14-cycle round-trips survive when T1 rotates\n");
  bp_print_string("across several separate stub entry points.\n\n");

  for (uint64_t trial = 0; trial < N_TRIALS; trial++) {
    uint64_t slot = trial & 0x3ULL;
    seed_thread(1, &t1_stack[STACK_WORDS], npcs[slot]);

    uint64_t elapsed = round_trip_once();
    total_cycles += elapsed;
    if (elapsed < min_cycles)
      min_cycles = elapsed;
    if (elapsed > max_cycles)
      max_cycles = elapsed;
    if (elapsed == 14)
      exact_14++;
    if (trial < 4)
      first_pass[trial] = elapsed;
  }

  restore_gp();
  bp_print_string("First pass slot 0:     ");
  bp_hprint_uint64(first_pass[0]);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("First pass slot 1:     ");
  bp_hprint_uint64(first_pass[1]);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("First pass slot 2:     ");
  bp_hprint_uint64(first_pass[2]);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("First pass slot 3:     ");
  bp_hprint_uint64(first_pass[3]);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("\nMin round-trip:        ");
  bp_hprint_uint64(min_cycles);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Max round-trip:        ");
  bp_hprint_uint64(max_cycles);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Avg round-trip:        ");
  bp_hprint_uint64(total_cycles / N_TRIALS);
  bp_print_string(" cycles\n");

  restore_gp();
  bp_print_string("Exact 14-cycle trials: ");
  bp_hprint_uint64(exact_14);
  bp_print_string(" / ");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\n");

  restore_gp();
  bp_print_string("Min single-switch:     ");
  bp_hprint_uint64(min_cycles / 2);
  bp_print_string(" cycles\n");

  bp_finish(0);
  return 0;
}
