/**
 * mt_ctxtsw_overhead_benchmark.c
 *
 * Measure both the raw steady-state context-switch spacing and the added
 * program overhead versus an equal-count no-switch instruction stream.
 *
 * The raw cycles/switch number answers: how far apart are back-to-back ctxtsw
 * dispatches in a hot ring?
 *
 * The normalized overhead number answers: how many extra cycles does each
 * inserted ctxtsw add compared with executing a normal instruction slot plus
 * equivalent loop bookkeeping?
 */

#include <stdint.h>
#include "bp_utils.h"

#define NUM_CONTEXTS 4
#define SWITCHES_PER_CONTEXT 256
#define UNROLL_FACTOR 4
#define LOOP_ITERS (SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define CONTROL_ITERS (NUM_CONTEXTS * LOOP_ITERS)
#define TOTAL_SWITCHES (NUM_CONTEXTS * SWITCHES_PER_CONTEXT)
#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x082, %0" : : "r"(v) : "memory");
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x083, %0" : : "r"(v) : "memory");
}

static inline void seed_thread(uint64_t tid, uint64_t *stack_top, uint64_t entry) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3, gp_val);
  seed_reg(tid, 2, (uint64_t)stack_top);
  seed_npc(tid, entry);
}

static void __attribute__((noinline)) control_loop(void) {
  for (uint64_t i = 0; i < CONTROL_ITERS; i++) {
    __asm__ volatile(
      "nop\n"
      "nop\n"
      "nop\n"
      "nop\n"
      : : : "memory"
    );
  }
}

void __attribute__((noinline, noreturn)) t1_ring(void) {
  for (uint64_t i = 0; i < LOOP_ITERS; i++) {
    __asm__ volatile(
      "csrwi 0x081, 2\n"
      "csrwi 0x081, 2\n"
      "csrwi 0x081, 2\n"
      "csrwi 0x081, 2\n"
      : : : "memory"
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
      : : : "memory"
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
      : : : "memory"
    );
  }

  for (;;)
    ;
}

int main(void) {
  uint64_t control_begin = read_cycle();
  control_loop();
  uint64_t control_end = read_cycle();
  uint64_t control_cycles = control_end - control_begin;

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  uint64_t switch_begin = read_cycle();
  for (uint64_t i = 0; i < LOOP_ITERS; i++) {
    __asm__ volatile(
      "csrwi 0x081, 1\n"
      "csrwi 0x081, 1\n"
      "csrwi 0x081, 1\n"
      "csrwi 0x081, 1\n"
      : : : "memory"
    );
  }
  uint64_t switch_end = read_cycle();
  uint64_t switch_cycles = switch_end - switch_begin;

  uint64_t raw_cycles_per_switch = switch_cycles / TOTAL_SWITCHES;
  uint64_t raw_cycles_per_switch_x100 = (switch_cycles * 100) / TOTAL_SWITCHES;
  uint64_t control_cycles_per_slot = control_cycles / TOTAL_SWITCHES;
  uint64_t control_cycles_per_slot_x100 = (control_cycles * 100) / TOTAL_SWITCHES;
  uint64_t overhead_cycles = switch_cycles - control_cycles;
  uint64_t overhead_cycles_per_switch = overhead_cycles / TOTAL_SWITCHES;
  uint64_t overhead_cycles_per_switch_x100 = (overhead_cycles * 100) / TOTAL_SWITCHES;

  bp_print_string("=== Context Switch Overhead Benchmark ===\n");
  bp_print_string("Contexts:                    ");
  bp_hprint_uint64(NUM_CONTEXTS);
  bp_print_string("\n");
  bp_print_string("Switches/context:            ");
  bp_hprint_uint64(SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Unroll factor:               ");
  bp_hprint_uint64(UNROLL_FACTOR);
  bp_print_string("\n");
  bp_print_string("Total switch slots:          ");
  bp_hprint_uint64(TOTAL_SWITCHES);
  bp_print_string("\n");
  bp_print_string("Control cycles:              ");
  bp_hprint_uint64(control_cycles);
  bp_print_string("\n");
  bp_print_string("Switch cycles:               ");
  bp_hprint_uint64(switch_cycles);
  bp_print_string("\n");
  bp_print_string("Control cycles/slot:         ");
  bp_hprint_uint64(control_cycles_per_slot);
  bp_print_string("\n");
  bp_print_string("Control cycles/slot x100:    ");
  bp_hprint_uint64(control_cycles_per_slot_x100);
  bp_print_string("\n");
  bp_print_string("Raw cycles/switch:           ");
  bp_hprint_uint64(raw_cycles_per_switch);
  bp_print_string("\n");
  bp_print_string("Raw cycles/switch x100:      ");
  bp_hprint_uint64(raw_cycles_per_switch_x100);
  bp_print_string("\n");
  bp_print_string("Added overhead/switch:       ");
  bp_hprint_uint64(overhead_cycles_per_switch);
  bp_print_string("\n");
  bp_print_string("Added overhead/switch x100:  ");
  bp_hprint_uint64(overhead_cycles_per_switch_x100);
  bp_print_string("\n");

  bp_finish(0);
  return 0;
}
