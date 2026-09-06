/**
 * mt_ctxtsw_pure_ring_stress_test.c
 *
 * Dense 4-context context-switch ring with no loop bookkeeping in the measured
 * stream. This is a stress/regression test, not a benchmark.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn, aligned(64))) t1_ring(void) {
  __asm__ volatile(
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "csrwi 0x800, 2\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t2_ring(void) {
  __asm__ volatile(
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "csrwi 0x800, 3\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn, aligned(64))) t3_ring(void) {
  __asm__ volatile(
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "csrwi 0x800, 0\n"
    "1:\n"
    "j 1b\n"
  );
}

int main(void) {
  bp_print_string("=== Pure Context-Switch Ring Stress Test ===\n");
  bp_print_string("4 contexts, 8 consecutive csrwi per context, no loop bookkeeping.\n");

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_ring);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_ring);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_ring);

  __asm__ volatile(
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
    "csrwi 0x800, 1\n"
  );

  bp_print_string("[BSG-PASS] pure ctxtsw ring stress completed\n");
  bp_finish(0);
  return 0;
}
