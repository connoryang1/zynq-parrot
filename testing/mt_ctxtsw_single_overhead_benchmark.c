/**
 * mt_ctxtsw_single_overhead_benchmark.c
 *
 * Measure a single context switch inserted between two hot straight-line
 * instruction streams. This complements the back-to-back ring benchmark:
 * it answers how much extra time one ctxtsw adds when surrounded by normal
 * work, rather than another ctxtsw.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define STREAM_REPS 128
#define TRIALS 16

#define REP2(op)   op op
#define REP4(op)   REP2(op) REP2(op)
#define REP8(op)   REP4(op) REP4(op)
#define REP16(op)  REP8(op) REP8(op)
#define REP32(op)  REP16(op) REP16(op)
#define REP64(op)  REP32(op) REP32(op)
#define REP128(op) REP64(op) REP64(op)
#define ALU_STREAM REP128("addi x0, x0, 0\n")

static uint64_t t1_stack[STACK_WORDS];

static volatile uint64_t control_cycles[TRIALS];
static volatile uint64_t switch_cycles[TRIALS];
static volatile uint64_t pre_switch_cycles[TRIALS];
static volatile uint64_t target_cycles[TRIALS];
static volatile uint64_t raw_redirect_cycles[TRIALS];
static volatile uint64_t switch_start_cycle;
static volatile uint64_t before_switch_cycle;
static volatile uint64_t current_trial;

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static void print_int64(int64_t v) {
  if (v < 0) {
    bp_print_string("-");
    bp_hprint_uint64((uint64_t)(-v));
  } else {
    bp_hprint_uint64((uint64_t)v);
  }
}

void __attribute__((noinline, noreturn, aligned(8))) t1_timed_entry(void) {
  uint64_t trial = current_trial;
  uint64_t target_begin = read_cycle();
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    ALU_STREAM
    ".option pop\n"
    : : : "memory"
  );
  uint64_t end = read_cycle();

  target_cycles[trial] = end - target_begin;
  raw_redirect_cycles[trial] = target_begin - before_switch_cycle;
  switch_cycles[trial] = end - switch_start_cycle;

  __asm__ volatile("csrwi 0x800, 0" : : : "memory");
  for (;;)
    ;
}

void __attribute__((noinline, noreturn, aligned(8))) t1_warm_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    ALU_STREAM
    ".option pop\n"
    "csrwi 0x800, 0\n"
    : : : "memory"
  );

  for (;;)
    ;
}

int main(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    ALU_STREAM
    ALU_STREAM
    ".option pop\n"
    : : : "memory"
  );

  uint64_t sp_val;
  __asm__ volatile("mv %0, sp" : "=r"(sp_val));
  seed_thread(0, (uint64_t *)sp_val, (uint64_t)&&after_warm_switch);
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_entry);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");

after_warm_switch:
  for (uint64_t trial = 0; trial < TRIALS; trial++) {
    uint64_t control_begin = read_cycle();
    __asm__ volatile(
      ".option push\n"
      ".option norvc\n"
      ALU_STREAM
      ALU_STREAM
      ".option pop\n"
      : : : "memory"
    );
    uint64_t control_end = read_cycle();
    control_cycles[trial] = control_end - control_begin;

    current_trial = trial;
    seed_thread(0, (uint64_t *)sp_val, (uint64_t)&&after_timed_switch);
    seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_timed_entry);

    uint64_t switch_begin = read_cycle();
    switch_start_cycle = switch_begin;
    __asm__ volatile(
      ".option push\n"
      ".option norvc\n"
      ALU_STREAM
      ".option pop\n"
      : : : "memory"
    );
    uint64_t before_switch = read_cycle();
    before_switch_cycle = before_switch;
    pre_switch_cycles[trial] = before_switch - switch_begin;
    __asm__ volatile("csrwi 0x800, 1" : : : "memory");

after_timed_switch:
    ;
  }

  uint64_t min_redirect = raw_redirect_cycles[0];
  uint64_t sum_redirect = 0;
  int64_t min_added = (int64_t)(switch_cycles[0] - control_cycles[0]);
  int64_t sum_added = 0;

  for (uint64_t trial = 0; trial < TRIALS; trial++) {
    int64_t added = (int64_t)(switch_cycles[trial] - control_cycles[trial]);
    if (raw_redirect_cycles[trial] < min_redirect)
      min_redirect = raw_redirect_cycles[trial];
    if (added < min_added)
      min_added = added;
    sum_redirect += raw_redirect_cycles[trial];
    sum_added += added;
  }

  bp_print_string("=== Single Context Switch Overhead Benchmark ===\n");
  bp_print_string("Stream reps per side:          ");
  bp_hprint_uint64(STREAM_REPS);
  bp_print_string("\n");
  bp_print_string("Trials:                        ");
  bp_hprint_uint64(TRIALS);
  bp_print_string("\n");
  bp_print_string("Min raw redirect cycles:       ");
  bp_hprint_uint64(min_redirect);
  bp_print_string("\n");
  bp_print_string("Avg raw redirect cycles:       ");
  bp_hprint_uint64(sum_redirect / TRIALS);
  bp_print_string("\n");
  bp_print_string("Min added total cycles:        ");
  print_int64(min_added);
  bp_print_string("\n");
  bp_print_string("Avg added total cycles:        ");
  print_int64(sum_added / TRIALS);
  bp_print_string("\n");
  bp_print_string("Last control cycles:           ");
  bp_hprint_uint64(control_cycles[TRIALS - 1]);
  bp_print_string("\n");
  bp_print_string("Last switch cycles:            ");
  bp_hprint_uint64(switch_cycles[TRIALS - 1]);
  bp_print_string("\n");

  bp_finish(0);
  for (;;)
    ;
}
