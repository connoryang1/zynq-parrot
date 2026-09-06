/**
 * mt_ctxtsw_logical_csr_readback_test.c
 *
 * Verifies that CSR 0x800 reports the committed logical context before,
 * during, and after a resident 0 -> 1 -> 0 context-switch round trip.
 * Repeated reads also prove that a read-only CSRRS does not launch a switch.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t t1_first_context;
static volatile uint64_t t1_second_context;
static volatile uint64_t t1_seen;

static inline uint64_t current_context(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x800" : "=r"(value));
  return value;
}

static inline void ctxtsw_to_0(void) {
  __asm__ volatile("csrwi 0x800, 0" ::: "memory");
}

static inline void ctxtsw_to_1(void) {
  __asm__ volatile("csrwi 0x800, 1" ::: "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  t1_first_context = current_context();
  t1_second_context = current_context();
  t1_seen = 1;
  ctxtsw_to_0();

  for (;;)
    ;
}

int main(void) {
  uint64_t t0_first_context = current_context();
  uint64_t t0_second_context = current_context();

  t1_first_context = ~0ULL;
  t1_second_context = ~0ULL;
  t1_seen = 0;
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);

  bp_print_string("=== logical context CSR round-trip test ===\n");
  ctxtsw_to_1();

  uint64_t t0_return_first_context = current_context();
  uint64_t t0_return_second_context = current_context();
  if ((t0_first_context != 0)
      || (t0_second_context != 0)
      || (t1_seen != 1)
      || (t1_first_context != 1)
      || (t1_second_context != 1)
      || (t0_return_first_context != 0)
      || (t0_return_second_context != 0)) {
    bp_print_string("[BSG-FAIL] logical context CSR did not report 0 -> 1 -> 0\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] logical context CSR reported 0 -> 1 -> 0\n");
  bp_finish(0);
  return 0;
}
