/**
 * mt_ctxtsw_8ctx_ring_throughput_benchmark.c
 *
 * Parameterized scale version of the ring throughput benchmark. This is a
 * probe for RTL elaborated with BP_NUM_THREADS > 4, not part of the default
 * four-context regression suite.
 *
 * This benchmark has two intended modes:
 *   - conservative/default: UNROLL_FACTOR=4, useful as a compact smoke-style
 *     throughput check with modest instruction footprint.
 *   - best-case reporting: UNROLL_FACTOR=256, SAME_LOOP_WARMUP=1,
 *     HOT_ALIGN_MODE=64, and WARMUP_SWITCHES_PER_CONTEXT=256, useful for the
 *     lowest measured hot-ring average seen on the 16-context traced model as
 *     of 2026-05-29.
 *
 * The software-visible rdcycle result is a ring throughput measurement:
 * ctxtsw dispatch to the next ctxtsw dispatch in the benchmark stream. It is
 * not the hardware handoff latency. Use tools/ctxtsw_perf_report.py on the
 * TRACE waveform for the primary hardware metric, d_first_instr_dispatch:
 * ctxtsw dispatch to the first target-context instruction dispatch.
 *
 * The raw hot handoff can dispatch the first target-context instruction in
 * 4 cycles, but loop bookkeeping and fetch footprint affect the program-level
 * average. A 16-context TRACE=1 sweep at SWITCHES_PER_CONTEXT=256,
 * WARMUP_SWITCHES_PER_CONTEXT=64 measured approximately:
 *   UNROLL_FACTOR=4   -> 5.26 cycles/switch
 *   UNROLL_FACTOR=8   -> 4.65 cycles/switch
 *   UNROLL_FACTOR=16  -> 4.87 cycles/switch
 *   UNROLL_FACTOR=32  -> 6.38 cycles/switch
 *   UNROLL_FACTOR=64  -> 6.64 cycles/switch
 *
 * SAME_LOOP_WARMUP=1 is a diagnostic/best-case mode that makes warmup and
 * measurement call the same noinline loop body so the measured instruction
 * addresses are warmed exactly. With UNROLL_FACTOR=8, SWITCHES_PER_CONTEXT=256,
 * and WARMUP_SWITCHES_PER_CONTEXT=64, the 16-context traced model measured:
 *   SAME_LOOP_WARMUP=0 -> 4.65 cycles/switch
 *   SAME_LOOP_WARMUP=1 -> 4.31 cycles/switch
 * The corresponding waveform still showed the hardware handoff at exactly
 * 4 cycles for every measured hot handoff; remaining software excess is loop
 * control / call-return / measurement-window overhead, not I-cache misses.
 * UNROLL_FACTOR=256 can be used with SWITCHES_PER_CONTEXT=256 to remove the
 * measured loop backedge entirely. With SAME_LOOP_WARMUP=1, HOT_ALIGN_MODE=64,
 * and WARMUP_SWITCHES_PER_CONTEXT=256, the 16-context traced model measured
 * approximately 4.10 cycles/switch in software. The shared same-loop body means
 * waveform tools must start at the measured post-rdcycle body entry, not the
 * first matching body PC from warmup. With that corrected window, the waveform
 * showed all 4096 expected dispatches, 100% I-cache hits, and 4-cycle hardware
 * first-instruction dispatch for every measured handoff.
 *
 * SWITCHES_PER_CONTEXT > 256 with UNROLL_FACTOR=256 runs the same 256-csrw
 * body multiple times per measured context. In this mode HOT_ALIGN_MODE=64
 * also aligns the inline-asm loop label itself; aligning only the function
 * entry let compiler loop setup shift the first csrw off the fetch boundary
 * and produced many 5-cycle handoffs. With the loop label aligned, the
 * 16-context traced model measured:
 *   SWITCHES_PER_CONTEXT=512  -> 4.067 cycles/switch, excess 548 cycles
 *   SWITCHES_PER_CONTEXT=1024 -> 4.040 cycles/switch, excess 663 cycles
 *   SWITCHES_PER_CONTEXT=2048 -> 4.024 cycles/switch, excess 791 cycles
 * Waveform windows starting at the measured body entry cycle showed 100%
 * I-cache hits, no abort samples, and every measured hardware
 * d_first_instr_dispatch at exactly 4 cycles. The remaining software excess is
 * d_next_ctxtsw loop/block-boundary overhead and can be further amortized by
 * increasing SWITCHES_PER_CONTEXT, with diminishing returns and longer traces.
 *
 * Waveform scans showed UNROLL_FACTOR=32 slowed down despite unchanged ctxtsw
 * commit latency: the larger hot body produced more FE queue delay and occasional
 * long I-cache/old-miss gaps. Do not assume larger unroll is better.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#ifndef NUM_CONTEXTS
#define NUM_CONTEXTS BP_NUM_THREADS
#endif

#if BP_NUM_THREADS < NUM_CONTEXTS
#error "NUM_CONTEXTS cannot exceed BP_NUM_THREADS"
#endif

#if NUM_CONTEXTS < 2
#error "NUM_CONTEXTS must be at least 2"
#endif

#ifndef SWITCHES_PER_CONTEXT
#define SWITCHES_PER_CONTEXT 128
#endif

#ifndef WARMUP_SWITCHES_PER_CONTEXT
#define WARMUP_SWITCHES_PER_CONTEXT 32
#endif

#ifndef UNROLL_FACTOR
#define UNROLL_FACTOR 4
#endif

#ifndef HOT_ALIGN_MODE
#define HOT_ALIGN_MODE 0
#endif

#ifndef SAME_LOOP_WARMUP
#define SAME_LOOP_WARMUP 0
#endif

#define WAVEFORM_HOT_FIRST_INSTR_DISPATCH_CYCLES 4

#define LOOP_ITERS (SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define WARMUP_LOOP_ITERS (WARMUP_SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define STACK_WORDS 512

#if (SWITCHES_PER_CONTEXT % UNROLL_FACTOR) != 0
#error "SWITCHES_PER_CONTEXT must be a multiple of UNROLL_FACTOR"
#endif

#if (WARMUP_SWITCHES_PER_CONTEXT % UNROLL_FACTOR) != 0
#error "WARMUP_SWITCHES_PER_CONTEXT must be a multiple of UNROLL_FACTOR"
#endif

#if (UNROLL_FACTOR != 4) && (UNROLL_FACTOR != 8) && (UNROLL_FACTOR != 16) && (UNROLL_FACTOR != 32) && (UNROLL_FACTOR != 64) && (UNROLL_FACTOR != 128) && (UNROLL_FACTOR != 256)
#error "UNROLL_FACTOR must be one of 4, 8, 16, 32, 64, 128, or 256"
#endif

#if (HOT_ALIGN_MODE != 0) && (HOT_ALIGN_MODE != 64)
#error "HOT_ALIGN_MODE must be 0 or 64"
#endif

#if (SAME_LOOP_WARMUP != 0) && (SAME_LOOP_WARMUP != 1)
#error "SAME_LOOP_WARMUP must be 0 or 1"
#endif

#if HOT_ALIGN_MODE == 64
#define HOT_CODE_ALIGN() __asm__ volatile(".p2align 6" ::: "memory")
#define HOT_FUNC __attribute__((noinline, aligned(64)))
#else
#define HOT_CODE_ALIGN() do { } while (0)
#define HOT_FUNC __attribute__((noinline))
#endif

/*
 * Keep the unroll factor compile-time constant so the measured body is a
 * straight-line run of csrw instructions. A runtime inner loop would reintroduce
 * branch/add bookkeeping into the hot path we are trying to amortize.
 */
#define REP2(op)  op op
#define REP4(op)  REP2(op) REP2(op)
#define REP8(op)  REP4(op) REP4(op)
#define REP16(op) REP8(op) REP8(op)
#define REP32(op) REP16(op) REP16(op)
#define REP64(op) REP32(op) REP32(op)
#define REP128(op) REP64(op) REP64(op)
#define REP256(op) REP128(op) REP128(op)

#define ASM_CSRW_NEXT "csrw 0x081, %[next]\n\t"
#define ASM_REP2(op)  op op
#define ASM_REP4(op)  ASM_REP2(op) ASM_REP2(op)
#define ASM_REP8(op)  ASM_REP4(op) ASM_REP4(op)
#define ASM_REP16(op) ASM_REP8(op) ASM_REP8(op)
#define ASM_REP32(op) ASM_REP16(op) ASM_REP16(op)
#define ASM_REP64(op) ASM_REP32(op) ASM_REP32(op)
#define ASM_REP128(op) ASM_REP64(op) ASM_REP64(op)
#define ASM_REP256(op) ASM_REP128(op) ASM_REP128(op)

#if UNROLL_FACTOR == 4
#define REP_UNROLL(op) REP4(op)
#elif UNROLL_FACTOR == 8
#define REP_UNROLL(op) REP8(op)
#elif UNROLL_FACTOR == 16
#define REP_UNROLL(op) REP16(op)
#elif UNROLL_FACTOR == 32
#define REP_UNROLL(op) REP32(op)
#elif UNROLL_FACTOR == 64
#define REP_UNROLL(op) REP64(op)
#elif UNROLL_FACTOR == 128
#define REP_UNROLL(op) REP128(op)
#elif UNROLL_FACTOR == 256
#define REP_UNROLL(op) REP256(op)
#endif

#if UNROLL_FACTOR == 4
#define ASM_REP_UNROLL(op) ASM_REP4(op)
#elif UNROLL_FACTOR == 8
#define ASM_REP_UNROLL(op) ASM_REP8(op)
#elif UNROLL_FACTOR == 16
#define ASM_REP_UNROLL(op) ASM_REP16(op)
#elif UNROLL_FACTOR == 32
#define ASM_REP_UNROLL(op) ASM_REP32(op)
#elif UNROLL_FACTOR == 64
#define ASM_REP_UNROLL(op) ASM_REP64(op)
#elif UNROLL_FACTOR == 128
#define ASM_REP_UNROLL(op) ASM_REP128(op)
#elif UNROLL_FACTOR == 256
#define ASM_REP_UNROLL(op) ASM_REP256(op)
#endif

static uint64_t stacks[NUM_CONTEXTS - 1][STACK_WORDS];

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static inline uint64_t read_context(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, 0x081" : "=r"(v));
  return v;
}

static inline void switch_context(uint64_t tid) {
  __asm__ volatile("csrw 0x081, %0" : : "r"(tid) : "memory");
}

#if SAME_LOOP_WARMUP
/*
 * Diagnostic mode: use one real function body for both the unmeasured warmup
 * call and the measured call. This warms the exact loop instruction addresses
 * being timed, unlike the default fully inlined mode where warmup and measured
 * call sites may occupy different I-cache lines.
 */
static void HOT_FUNC ring_switch_loop(uint64_t next_tid, uint64_t iters) {
#else
static inline __attribute__((always_inline)) void ring_switch_loop(uint64_t next_tid,
                                                                   uint64_t iters) {
#endif
#if SAME_LOOP_WARMUP && (UNROLL_FACTOR == 256) && (HOT_ALIGN_MODE == 64)
  /*
   * For multi-iteration full-unroll experiments, align the actual loop label,
   * not only the function entry. Otherwise the compiler's loop-counter prologue
   * can shift the first csrw off the desired fetch boundary.
   */
  __asm__ volatile(
      "mv t0, %[iters]\n\t"
      ".p2align 3\n"
      "1:\n\t"
      ASM_REP_UNROLL(ASM_CSRW_NEXT)
      "addi t0, t0, -1\n\t"
      "bnez t0, 1b\n\t"
      :
      : [next] "r"(next_tid), [iters] "r"(iters)
      : "t0", "memory");
#else
  for (uint64_t i = 0; i < iters; i++) {
    REP_UNROLL(switch_context(next_tid);)
  }
#endif
}

void HOT_FUNC __attribute__((noreturn)) ring_worker(void) {
  uint64_t next_tid = read_context() + 1;

  if (next_tid == NUM_CONTEXTS)
    next_tid = 0;

  HOT_CODE_ALIGN();
  ring_switch_loop(next_tid, WARMUP_LOOP_ITERS);
  HOT_CODE_ALIGN();
  ring_switch_loop(next_tid, LOOP_ITERS);

  HOT_CODE_ALIGN();
  for (;;)
    switch_context(next_tid);
}

int HOT_FUNC main(void) {
  for (uint64_t tid = 1; tid < NUM_CONTEXTS; tid++)
    seed_thread(tid, &stacks[tid - 1][STACK_WORDS], (uint64_t)ring_worker);

  HOT_CODE_ALIGN();
  ring_switch_loop(1, WARMUP_LOOP_ITERS);

  HOT_CODE_ALIGN();
  uint64_t begin = read_cycle();
  ring_switch_loop(1, LOOP_ITERS);
  uint64_t end = read_cycle();

  uint64_t diff = end - begin;
  uint64_t num_switches = NUM_CONTEXTS * SWITCHES_PER_CONTEXT;
  uint64_t cycles_per_switch = diff / num_switches;
  uint64_t ideal_4cycle_total = 4 * num_switches;
  uint64_t excess_over_4cycle = (diff > ideal_4cycle_total) ? (diff - ideal_4cycle_total) : 0;

  bp_print_string("=== Scale Context Ring Throughput Benchmark ===\n");
  bp_print_string("Loop bookkeeping amortized across multiple switches\n");
  bp_print_string("Contexts:             ");
  bp_hprint_uint64(NUM_CONTEXTS);
  bp_print_string("\n");
  bp_print_string("Switches/context:     ");
  bp_hprint_uint64(SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Warmup switches/ctx:  ");
  bp_hprint_uint64(WARMUP_SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Unroll factor:        ");
  bp_hprint_uint64(UNROLL_FACTOR);
  bp_print_string("\n");
  bp_print_string("Same-loop warmup:     ");
  bp_hprint_uint64(SAME_LOOP_WARMUP);
  bp_print_string("\n");
  bp_print_string("Total cycles:         ");
  bp_hprint_uint64(diff);
  bp_print_string("\n");
  bp_print_string("Total switches:       ");
  bp_hprint_uint64(num_switches);
  bp_print_string("\n");
  bp_print_string("Measured throughput cyc/switch: ");
  bp_hprint_uint64(cycles_per_switch);
  bp_print_string("\n");
  bp_print_string("Excess cycles over 4/switch: ");
  bp_hprint_uint64(excess_over_4cycle);
  bp_print_string("\n");
  bp_print_string("Expected TRACE hot first-instr dispatch: ");
  bp_hprint_uint64(WAVEFORM_HOT_FIRST_INSTR_DISPATCH_CYCLES);
  bp_print_string("\n");

  bp_finish(0);
  return 0;
}
