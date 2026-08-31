/**
 * mt_ctxtsw_nonresident_overhead_benchmark.c
 *
 * Compare resident-hit versus nonresident-miss steady-state context-switch
 * behavior with the current implementation.
 *
 * Warm path: logical contexts 0 and 1 are resident at reset, so 0 <-> 1 uses
 * the existing resident-hit forwarding path.
 *
 * Cold path: logical context 2 is nonresident at reset. Repeated 0 <-> 2
 * switching forces the slow restore path on every switch because each switch
 * evicts the previous logical owner of the physical slot. The nonresident
 * elapsed cost is measured with the core-wide physical cycle CSR. Unlike
 * rdcycle/mcycle, CSR 0xCC0 is not part of the virtual context image, so the
 * same measurement works in simulation and on the FPGA.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define SWITCHES_PER_CONTEXT 128
#define UNROLL_FACTOR 32
#define LOOP_ITERS (SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define TOTAL_SWITCHES (2 * SWITCHES_PER_CONTEXT)

#define REP2(op)  op op
#define REP4(op)  REP2(op) REP2(op)
#define REP8(op)  REP4(op) REP4(op)
#define REP16(op) REP8(op) REP8(op)
#define REP32(op) REP16(op) REP16(op)
#define STR2(x) #x
#define STR(x) STR2(x)

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];

static inline uint64_t read_global_cycle(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(v) :: "memory");
  return v;
}

static void __attribute__((noinline, aligned(8))) t0_warm_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP32("csrwi 0x800, 1\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );
}

void __attribute__((noinline, noreturn, aligned(8))) t1_warm_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP32("csrwi 0x800, 0\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );

  for (;;)
    ;
}

static void __attribute__((noinline, aligned(8))) t0_cold_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP32("csrwi 0x800, 2\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );
}

void __attribute__((noinline, noreturn, aligned(8))) t2_cold_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n"
    "1:\n"
    REP32("csrwi 0x800, 0\n")
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    : : : "t0", "memory"
  );

  for (;;)
    ;
}

int main(void) {
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_ring);
  t0_warm_ring();

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_ring);
  uint64_t warm_begin = read_global_cycle();
  t0_warm_ring();
  uint64_t warm_end = read_global_cycle();
  uint64_t warm_cycles = warm_end - warm_begin;

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_ring);
  t0_cold_ring();

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_ring);
  uint64_t cold_begin = read_global_cycle();
  t0_cold_ring();
  uint64_t cold_end = read_global_cycle();
  uint64_t cold_cycles = cold_end - cold_begin;

  uint64_t warm_cycles_per_switch = warm_cycles / TOTAL_SWITCHES;
  uint64_t warm_cycles_per_switch_x100 = (warm_cycles * 100) / TOTAL_SWITCHES;
  uint64_t cold_cycles_per_switch = cold_cycles / TOTAL_SWITCHES;
  uint64_t cold_cycles_per_switch_x100 = (cold_cycles * 100) / TOTAL_SWITCHES;
  uint64_t added_cycles = cold_cycles - warm_cycles;
  uint64_t added_cycles_per_switch_x100 = (added_cycles * 100) / TOTAL_SWITCHES;

  bp_print_string("=== Nonresident Context Switch Overhead Benchmark ===\n");
  bp_print_string("Switches/context:                ");
  bp_hprint_uint64(SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Unroll factor:                   ");
  bp_hprint_uint64(UNROLL_FACTOR);
  bp_print_string("\n");
  bp_print_string("Total switches measured:         ");
  bp_hprint_uint64(TOTAL_SWITCHES);
  bp_print_string("\n");
  bp_print_string("Warm total cycles:               ");
  bp_hprint_uint64(warm_cycles);
  bp_print_string("\n");
  bp_print_string("Warm cycles/switch:              ");
  bp_hprint_uint64(warm_cycles_per_switch);
  bp_print_string("\n");
  bp_print_string("Warm cycles/switch x100:         ");
  bp_hprint_uint64(warm_cycles_per_switch_x100);
  bp_print_string("\n");
  bp_print_string("Cold total cycles:               ");
  bp_hprint_uint64(cold_cycles);
  bp_print_string("\n");
  bp_print_string("Cold cycles/switch:              ");
  bp_hprint_uint64(cold_cycles_per_switch);
  bp_print_string("\n");
  bp_print_string("Cold cycles/switch x100:         ");
  bp_hprint_uint64(cold_cycles_per_switch_x100);
  bp_print_string("\n");
  bp_print_string("Cold minus warm cycles/switch x100: ");
  bp_hprint_uint64(added_cycles_per_switch_x100);
  bp_print_string("\n");
  bp_print_string("\n");

  bp_finish(0);
  return 0;
}
