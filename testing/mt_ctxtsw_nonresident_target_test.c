/**
 * mt_ctxtsw_nonresident_target_test.c
 *
 * Minimal positive probe for resident-miss context-cache plumbing. Build/run
 * with NUM_THREADS=2 NUM_CONTEXTS=4. Context IDs 0/1 are resident hardware
 * slots at reset; context ID 2 is logical-only and must be restored through
 * the context-cache slow path.
 */

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256

static uint64_t t2_stack[STACK_WORDS];
static volatile uint64_t t2_seen;

static inline void ctxtsw_to_0(void) {
  __asm__ volatile("csrwi 0x800, 0" ::: "memory");
}

static inline void ctxtsw_to_2(void) {
  __asm__ volatile("csrwi 0x800, 2" ::: "memory");
}

void __attribute__((noinline, noreturn)) t2_entry(void) {
  t2_seen = 1;
  ctxtsw_to_0();

  for (;;)
    ;
}

int main(void) {
  t2_seen = 0;
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);

  ctxtsw_to_2();

  if (t2_seen != 1) {
    bp_print_string("[BSG-FAIL] logical context 2 did not run\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] nonresident context switch completed\n");
  bp_finish(0);
  return 0;
}
