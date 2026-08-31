/**
 * mt_ctxtsw_predictor_pollution.c
 *
 * Measures whether T1's branch pattern pollutes T0's branch predictor.
 *
 * BlackParrot's BTB and BHT are per-thread (N instances via genvar), so
 * switching to T1 should not corrupt T0's entries. The GHR is SHARED, so
 * T1's branches can alter which BHT row T0's branch hits after resuming.
 *
 * Method:
 *   1. T0 warms the predictor with a tight always-taken loop (baseline).
 *   2. T0 times N iterations of the same loop (pre-switch latency).
 *   3. T0 switches to T1. T1 runs an alternating taken/not-taken loop
 *      to scramble the shared GHR.
 *   4. T1 returns to T0.
 *   5. T0 times the same loop again (post-switch latency).
 *   6. Reports both latencies; a significant increase indicates GHR pollution.
 *      With per-thread GHR the numbers should be identical.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS  512
#define LOOP_ITERS   256
#define WARMUP_REPS  4
#define MEASURE_REPS 8

static uint64_t t1_stack[STACK_WORDS];

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static inline void restore_gp(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la gp, __global_pointer$\n"
    ".option pop\n"
    : : : "gp"
  );
}

/* Always-taken backward branch loop — trains BTB/BHT to predict taken. */
static __attribute__((noinline)) uint64_t time_taken_loop(uint64_t iters) {
  uint64_t count = iters;
  uint64_t start = read_cycle();
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "1: addi %0, %0, -1\n"
    "   bnez %0, 1b\n"
    ".option pop\n"
    : "+r"(count)
    :
    : "memory"
  );
  return read_cycle() - start;
}

/* Alternating taken/not-taken loop — scrambles the shared GHR. */
void __attribute__((naked, noinline, noreturn)) t1_pollute(void) {
  __asm__ volatile(
    "li   t1, 512\n"        /* iteration count */
    "1:\n"
    "addi t1, t1, -1\n"
    "andi t2, t1, 1\n"      /* LSB of count */
    "bnez t2, 1b\n"         /* taken on odd counts, falls through on even */
    "bnez t1, 1b\n"         /* outer always-taken until count reaches 0 */
    "csrwi 0x800, 0\n"      /* switch back to T0 */
    "1:\n"
    "j 1b\n"
    :
    :
    : "t1", "t2"
  );
}

int main(void) {
  bp_print_string("=== Predictor Pollution Benchmark ===\n");
  bp_print_string("BTB/BHT: per-thread (should NOT be polluted)\n");
  bp_print_string("GHR:     shared (MAY be polluted by T1's alternating branch)\n\n");

  /* Warmup: bring the loop into I$ and train BTB/BHT in T0's per-thread tables */
  for (uint64_t i = 0; i < WARMUP_REPS; i++)
    time_taken_loop(LOOP_ITERS);

  /* Pre-switch measurement */
  uint64_t pre_min = ~0ULL;
  for (uint64_t i = 0; i < MEASURE_REPS; i++) {
    uint64_t t = time_taken_loop(LOOP_ITERS);
    if (t < pre_min) pre_min = t;
  }

  /* Switch to T1; T1 scrambles GHR with alternating branches */
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_pollute);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");
  /* T0 resumes here */

  restore_gp();

  /* Post-switch measurement using the same loop */
  uint64_t post_min = ~0ULL;
  for (uint64_t i = 0; i < MEASURE_REPS; i++) {
    uint64_t t = time_taken_loop(LOOP_ITERS);
    if (t < post_min) post_min = t;
  }

  bp_print_string("Loop iters per measurement: ");
  bp_hprint_uint64(LOOP_ITERS);
  bp_print_string("\n");
  bp_print_string("Measurement reps:           ");
  bp_hprint_uint64(MEASURE_REPS);
  bp_print_string("\n\n");

  bp_print_string("Pre-switch  min cycles:  ");
  bp_hprint_uint64(pre_min);
  bp_print_string("\n");
  bp_print_string("Post-switch min cycles:  ");
  bp_hprint_uint64(post_min);
  bp_print_string("\n");

  uint64_t delta;
  int increased;
  if (post_min > pre_min) {
    delta = post_min - pre_min;
    increased = 1;
  } else {
    delta = pre_min - post_min;
    increased = 0;
  }
  bp_print_string("Delta (post - pre):      ");
  if (increased) bp_print_string("+");
  else           bp_print_string("-");
  bp_hprint_uint64(delta);
  bp_print_string(" cycles\n\n");

  bp_print_string("Interpretation:\n");
  bp_print_string("  delta ~0  => GHR effectively per-thread (or pollution negligible)\n");
  bp_print_string("  delta >>0 => shared GHR polluted by T1's alternating pattern\n");

  bp_finish(0);
  return 0;
}
