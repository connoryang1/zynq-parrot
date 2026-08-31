/**
 * mt_ctxtsw_banyan_poll_worker_benchmark.c
 *
 * Banyan-style Benchmark: Poller (T0) + Worker (T1)
 *
 * Models the reference benchmark from the Banyan paper (Krzanich, Xu, Humphries):
 *   - T0 (poller): writes a request token to shared memory, switches to T1
 *   - T1 (worker): does WORK_ITERS iterations of synthetic branch+arithmetic work,
 *                  writes result and response token, switches back to T0
 *   - Measurement: rdcycle brackets one full T0→T1→T0 trip including the work
 *
 * Banyan baseline: ~139 cycles round-trip (2 context switches + shared memory
 * writes + 10 cycles of synthetic work).
 *
 * BTB/BHT isolation check: T1's inner work loop has a branch that T1's private
 * BTB/BHT can learn. On warm trials (3+), T1's loop branch should predict
 * correctly without being evicted by T0's branches. Compare cold (trial 0)
 * vs warm (trial 3+) — a lower warm latency confirms per-thread BTB/BHT benefit.
 *
 * Synthetic work: WORK_ITERS steps of a Collatz-like sequence
 *   (if odd: 3x+1; if even: x/2) — generates a branch per iteration.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define N_TRIALS    8
#define WORK_ITERS  10   /* matches Banyan's "10 cycles of work" */

#define STACK_WORDS 512
static uint64_t t1_stack[STACK_WORDS];

/* Shared communication area (T0 writes request; T1 writes result/response) */
static volatile uint64_t shared_request  = 0;
static volatile uint64_t shared_response = 0;
static volatile uint64_t work_result     = 0;

static inline void write_ctxt_0(void) {
  __asm__ volatile("csrwi 0x800, 0" : : : "memory");
}

static inline void write_ctxt_1(void) {
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");
}

static inline uint64_t read_mhartid(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, mhartid" : "=r"(v) : : "memory");
  return v;
}

static inline uint64_t read_ctxt(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, 0x800" : "=r"(v) : : "memory");
  return v;
}

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

/* ── Worker thread (T1) ──
 *
 * Runs in a persistent loop: each activation reads the shared request,
 * does WORK_ITERS steps of branch+arithmetic, writes result, then returns
 * to T0. T1's saved PC (after the csrw) lets it resume the loop correctly
 * on the next write_ctxt(1) from T0.
 *
 * The inner loop's branch is the target for BTB/BHT warm-up: after a few
 * activations T1's private predictor should know the branch pattern.
 */
void __attribute__((naked, noinline, noreturn)) t1_worker(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la   gp, __global_pointer$\n"
    ".option pop\n"
    "la   sp, t1_stack\n"
    "li   t0, %0\n"
    "add  sp, sp, t0\n"
    "call t1_worker_body\n"
    "1:\n"
    "j    1b\n"
    :
    : "i"(STACK_WORDS * 8)
    : "t0"
  );
}

void __attribute__((noinline, noreturn)) t1_worker_body(void) {
  while (1) {
    uint64_t acc = shared_request;

    /* Synthetic work: WORK_ITERS steps of Collatz-like sequence.
     * Generates one branch per iteration → exercises T1's BHT. */
    for (int i = 0; i < WORK_ITERS; i++) {
      if (acc & 1)
        acc = acc * 3 + 1;
      else
        acc = acc >> 1;
    }

    work_result     = acc;
    shared_response = shared_request + 1;   /* response token = req + 1 */

    write_ctxt_0();  /* switch back to T0; T1 resumes here next activation */
  }
  bp_finish(1);  /* unreachable */
}

int main(void) {
  uint64_t ctxt = read_ctxt();

  if (ctxt == 1) {
    t1_worker();
  }

  if (ctxt != 0 || read_mhartid() != 0) {
    /*
     * The bare-metal startup path can let non-driver hardware contexts reach
     * main. Keep T0 as the only poller/driver; T1 is the worker above.
     */
    for (;;)
      ;
  }

  bp_print_string("=== Banyan-style Benchmark: Poller+Worker ===\n");
  bp_print_string("T0=poller, T1=worker, work_iters=");
  bp_hprint_uint64(WORK_ITERS);
  bp_print_string(", trials=");
  bp_hprint_uint64(N_TRIALS);
  bp_print_string("\nBanyan baseline: ~139 cycles round-trip\n\n");

  /* Seed T1 once.  GP must match T0 so GP-relative globals work correctly. */
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));
  seed_reg(1, 3 /* x3=gp */, gp_val);
  seed_reg(1, 2 /* x2=sp */, (uint64_t)&t1_stack[STACK_WORDS]);
  seed_npc(1, (uint64_t)t1_worker);

  uint64_t min_cycles  = 0xFFFFFFFFFFFFFFFFULL;
  uint64_t warm_min    = 0xFFFFFFFFFFFFFFFFULL;
  uint64_t total       = 0;
  uint64_t cold_cycles = 0;

  for (int trial = 0; trial < N_TRIALS; trial++) {
    /* T0: write request token to shared page */
    shared_request  = (uint64_t)trial + 1;
    shared_response = 0;

    /* Measure full round-trip: T0 → T1 (work) → T0 */
    uint64_t before = read_cycle();
    write_ctxt_1();
    /* T0 resumes here after T1 calls write_ctxt(0) */
    uint64_t after = read_cycle();

    uint64_t elapsed = after - before;
    total += elapsed;
    if (elapsed < min_cycles) min_cycles = elapsed;
    if (trial == 0)           cold_cycles = elapsed;
    if (trial >= 3 && elapsed < warm_min) warm_min = elapsed;

    bp_print_string("Trial ");
    bp_hprint_uint64((uint64_t)trial);
    bp_print_string(": ");
    bp_hprint_uint64(elapsed);
    bp_print_string(" cycles  result=");
    bp_hprint_uint64(work_result);
    bp_print_string(" resp=");
    bp_hprint_uint64(shared_response);
    bp_print_string("\n");
  }

  bp_print_string("\nCold (trial 0):        ");
  bp_hprint_uint64(cold_cycles);
  bp_print_string(" cycles\n");

  if (N_TRIALS > 3) {
    bp_print_string("Warm min (trial 3+):   ");
    bp_hprint_uint64(warm_min);
    bp_print_string(" cycles\n");
  }

  bp_print_string("Overall min:           ");
  bp_hprint_uint64(min_cycles);
  bp_print_string(" cycles\n");

  bp_print_string("Avg:                   ");
  bp_hprint_uint64(total / N_TRIALS);
  bp_print_string(" cycles\n");

  bp_print_string("\nBanyan target:         ~139 cycles\n");
  bp_print_string("Single-switch target:  ~7 cycles (per Banyan paper)\n");

  /* Correctness check: last trial response = N_TRIALS + 1 */
  int errors = 0;
  uint64_t expected_resp = (uint64_t)(N_TRIALS + 1);
  if (shared_response != expected_resp) {
    bp_print_string("FAIL: response mismatch, got ");
    bp_hprint_uint64(shared_response);
    bp_print_string(" expected ");
    bp_hprint_uint64(expected_resp);
    bp_print_string("\n");
    errors++;
  }

  bp_print_string("\n");
  if (errors == 0) {
    bp_print_string("[BSG-PASS] Banyan benchmark complete\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] Banyan benchmark failed\n");
    bp_finish(1);
  }

  return 0;
}
