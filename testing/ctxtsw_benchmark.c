/*
 * Best-case resident context-switch throughput benchmark.
 *
 * Hardcoded reporting setup:
 *   - 16 resident hardware contexts
 *   - 256 warmup switches per context
 *   - 256 measured switches per context
 *   - one fully unrolled hot block, no timed loop branch
 *   - 64-byte function alignment and 8-byte first-csrw alignment
 *
 * This measures software-visible ring throughput with rdcycle. It should be
 * close to, but not exactly, the waveform handoff latency. The waveform metric
 * we report separately is ctxtsw dispatch to first useful target dispatch,
 * which is 4 cycles in the hot 16-context run.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS < 16
#error "ctxtsw_benchmark requires a 16-context simulator"
#endif

enum {
  NUM_CONTEXTS = 16,
  STACK_WORDS = 512,
  WARMUP_SWITCHES_PER_CONTEXT = 256,
  MEASURED_SWITCHES_PER_CONTEXT = 256,
  UNROLLED_SWITCHES = 256,
  HOT_HANDOFF_CYCLES = 4
};

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

static void __attribute__((noinline, aligned(64)))
ring_switch_256(uint64_t next_tid) {
  __asm__ volatile(
    ".p2align 3\n"
    ".rept 256\n"
    "csrw 0x081, %[next]\n"
    ".endr\n"
    :
    : [next] "r"(next_tid)
    : "memory");
}

void __attribute__((noreturn, noinline, aligned(64))) ring_worker(void) {
  uint64_t next_tid = read_context() + 1;

  if (next_tid == NUM_CONTEXTS)
    next_tid = 0;

  ring_switch_256(next_tid);
  ring_switch_256(next_tid);

  for (;;)
    switch_context(next_tid);
}

int __attribute__((aligned(64))) main(void) {
  for (uint64_t tid = 1; tid < NUM_CONTEXTS; tid++)
    seed_thread(tid, &stacks[tid - 1][STACK_WORDS], (uint64_t)ring_worker);

  ring_switch_256(1);

  uint64_t begin = read_cycle();
  ring_switch_256(1);
  uint64_t end = read_cycle();

  uint64_t total_cycles = end - begin;
  uint64_t total_switches = NUM_CONTEXTS * MEASURED_SWITCHES_PER_CONTEXT;
  uint64_t ideal_cycles = HOT_HANDOFF_CYCLES * total_switches;
  uint64_t excess_cycles = total_cycles - ideal_cycles;
  uint64_t cycles_per_switch_x1000 = (total_cycles * 1000) / total_switches;

  bp_print_string("=== Best-Case Context Switch Benchmark ===\n");
  bp_print_string("Contexts:             ");
  bp_hprint_uint64(NUM_CONTEXTS);
  bp_print_string("\n");
  bp_print_string("Switches/context:     ");
  bp_hprint_uint64(MEASURED_SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Warmup switches/ctx:  ");
  bp_hprint_uint64(WARMUP_SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Unroll factor:        ");
  bp_hprint_uint64(UNROLLED_SWITCHES);
  bp_print_string("\n");
  bp_print_string("Total cycles:         ");
  bp_hprint_uint64(total_cycles);
  bp_print_string("\n");
  bp_print_string("Total switches:       ");
  bp_hprint_uint64(total_switches);
  bp_print_string("\n");
  bp_print_string("Measured throughput cyc/switch: ");
  bp_hprint_uint64(total_cycles / total_switches);
  bp_print_string("\n");
  bp_print_string("Measured throughput cyc/switch x1000: ");
  bp_hprint_uint64(cycles_per_switch_x1000);
  bp_print_string("\n");
  bp_print_string("Excess cycles over 4/switch: ");
  bp_hprint_uint64(excess_cycles);
  bp_print_string("\n");
  bp_print_string("Expected TRACE hot first-instr dispatch: ");
  bp_hprint_uint64(HOT_HANDOFF_CYCLES);
  bp_print_string("\n");

  bp_finish(0);
  return 0;
}
