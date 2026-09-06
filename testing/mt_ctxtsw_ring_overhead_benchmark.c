/**
 * mt_ctxtsw_ring_overhead_benchmark.c
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
#include "mt_seed.h"

#define NUM_CONTEXTS 4
#define SWITCHES_PER_CONTEXT 256
#define UNROLL_FACTOR 64
#define LOOP_ITERS (SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define CONTROL_ITERS (NUM_CONTEXTS * LOOP_ITERS)
#define TOTAL_SWITCHES (NUM_CONTEXTS * SWITCHES_PER_CONTEXT)
#define STACK_WORDS 512

#define REP2(op)  op op
#define REP4(op)  REP2(op) REP2(op)
#define REP8(op)  REP4(op) REP4(op)
#define REP16(op) REP8(op) REP8(op)
#define REP32(op) REP16(op) REP16(op)
#define REP64(op) REP32(op) REP32(op)
#define STR2(x) #x
#define STR(x) STR2(x)

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

static void __attribute__((noinline, aligned(8))) control_loop(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(CONTROL_ITERS) "\n"
    "1:\n"
    REP64("addi x0, x0, 0\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );
}

static void __attribute__((noinline, aligned(8))) t0_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP64("csrwi 0x800, 1\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );
}

void __attribute__((noinline, noreturn, aligned(8))) t1_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP64("csrwi 0x800, 2\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );

  for (;;)
    ;
}

void __attribute__((noinline, noreturn, aligned(8))) t2_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP64("csrwi 0x800, 3\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );

  for (;;)
    ;
}

void __attribute__((noinline, noreturn, aligned(8))) t3_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP64("csrwi 0x800, 0\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );

  for (;;)
    ;
}

int main(void) {
  control_loop();

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);
  t0_ring();

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  uint64_t control_begin = read_cycle();
  control_loop();
  uint64_t control_end = read_cycle();
  uint64_t control_cycles = control_end - control_begin;

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  uint64_t switch_begin = read_cycle();
  t0_ring();
  uint64_t switch_end = read_cycle();
  uint64_t switch_cycles = switch_end - switch_begin;

  uint64_t raw_cycles_per_switch = switch_cycles / TOTAL_SWITCHES;
  uint64_t raw_cycles_per_switch_x100 = (switch_cycles * 100) / TOTAL_SWITCHES;
  uint64_t control_cycles_per_slot = control_cycles / TOTAL_SWITCHES;
  uint64_t control_cycles_per_slot_x100 = (control_cycles * 100) / TOTAL_SWITCHES;
  uint64_t overhead_cycles = switch_cycles - control_cycles;
  uint64_t overhead_cycles_per_switch = overhead_cycles / TOTAL_SWITCHES;
  uint64_t overhead_cycles_per_switch_x100 = (overhead_cycles * 100) / TOTAL_SWITCHES;

  bp_print_string("=== Context Switch Ring Overhead Benchmark ===\n");
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
