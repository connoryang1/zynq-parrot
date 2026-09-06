/**
 * Compare resident-hit and nonresident-miss context-switch throughput using
 * the core-wide physical cycle counter. The global counter is not restored
 * with virtual context state, so this measurement remains monotonic.
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

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

static void __attribute__((noinline, aligned(8))) t0_warm_ring(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n1:\n"
    REP32("csrwi 0x800, 1\n")
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"
    : : : "t0", "memory");
}

void __attribute__((noinline, noreturn, aligned(8))) t1_warm_ring(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n1:\n"
    REP32("csrwi 0x800, 0\n")
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"
    : : : "t0", "memory");
  for (;;)
    ;
}

static void __attribute__((noinline, aligned(8))) t0_cold_ring(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n1:\n"
    REP32("csrwi 0x800, 2\n")
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"
    : : : "t0", "memory");
}

void __attribute__((noinline, noreturn, aligned(8))) t2_cold_ring(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, " STR(LOOP_ITERS) "\n1:\n"
    REP32("csrwi 0x800, 0\n")
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n"
    : : : "t0", "memory");
  for (;;)
    ;
}

int main(void)
{
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_ring);
  t0_warm_ring();
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_ring);
  uint64_t warm_begin = read_global_cycle();
  t0_warm_ring();
  uint64_t warm_cycles = read_global_cycle() - warm_begin;

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_ring);
  t0_cold_ring();
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_ring);
  uint64_t cold_begin = read_global_cycle();
  t0_cold_ring();
  uint64_t cold_cycles = read_global_cycle() - cold_begin;

  bp_print_string("=== Nonresident Context Switch Overhead Benchmark ===\n");
  bp_print_string("Switches/context:                ");
  bp_hprint_uint64(SWITCHES_PER_CONTEXT);
  bp_print_string("\nWarm cycles/switch x100:         ");
  bp_hprint_uint64((warm_cycles * 100) / TOTAL_SWITCHES);
  bp_print_string("\nCold cycles/switch x100:         ");
  bp_hprint_uint64((cold_cycles * 100) / TOTAL_SWITCHES);
  bp_print_string("\nCold minus warm cycles/switch x100: ");
  bp_hprint_uint64(((cold_cycles - warm_cycles) * 100) / TOTAL_SWITCHES);
  bp_print_string("\n");
  bp_finish(0);
  return 0;
}
