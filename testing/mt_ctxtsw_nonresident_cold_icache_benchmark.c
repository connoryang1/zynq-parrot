/**
 * mt_ctxtsw_nonresident_cold_icache_benchmark.c
 *
 * Produce a controlled sequence of nonresident context switches whose target
 * instruction line is absent from the I-cache. Each logical context executes
 * fence.i, then a 128-instruction runway that lets cache maintenance retire
 * before the switch while the separately aligned target loop remains cold.
 * Contexts 0 and 2 alias the same physical resident slot. Interpret latency
 * from TRACE global-cycle markers because context restore virtualizes mcycle.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define SWITCHES_PER_CONTEXT 4
#define STR2(x) #x
#define STR(x) STR2(x)

static uint64_t t2_stack[STACK_WORDS];

void __attribute__((naked, noinline, aligned(4096))) t0_cold_icache_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(SWITCHES_PER_CONTEXT) "\n"
    "1:\n"
    "fence.i\n"
    /* Do not overlap the serializing fence and context-switch CSR. */
    ".rept 128\n"
    "nop\n"
    ".endr\n"
    "csrwi 0x800, 2\n"
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    "ret\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(4096))) t2_cold_icache_ring(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, " STR(SWITCHES_PER_CONTEXT) "\n"
    "1:\n"
    "fence.i\n"
    /* Do not overlap the serializing fence and context-switch CSR. */
    ".rept 128\n"
    "nop\n"
    ".endr\n"
    "csrwi 0x800, 0\n"
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    ".option pop\n"
    "1:\n"
    "j 1b\n"
  );
}

int main(void) {
  bp_print_string("=== Nonresident Cold-I-cache Context Switch Benchmark ===\n");
  bp_print_string("Switches/context:                ");
  bp_hprint_uint64(SWITCHES_PER_CONTEXT);
  bp_print_string("\n");
  bp_print_string("Expected TRACE switches:         ");
  bp_hprint_uint64(2 * SWITCHES_PER_CONTEXT);
  bp_print_string("\n");

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_icache_ring);
  t0_cold_icache_ring();

  bp_finish(0);
  return 0;
}
