/**
 * mt_ctxtsw_smoke_test.c
 *
 * Minimal context-switch hang sentinel.
 *
 * This intentionally avoids benchmarking. It only proves that one seeded
 * thread can be entered and can switch back to thread 0.
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 256

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t t1_seen;

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x082, %0" : : "r"(v));
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x083, %0" : : "r"(v));
}

static inline void seed_thread(uint64_t tid, uint64_t *stack_top, uint64_t entry) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, entry);
}

static inline void ctxtsw_to_0(void) {
  __asm__ volatile("csrwi 0x081, 0" ::: "memory");
}

static inline void ctxtsw_to_1(void) {
  __asm__ volatile("csrwi 0x081, 1" ::: "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  t1_seen = 1;
  ctxtsw_to_0();

  for (;;)
    ;
}

int main(void) {
  t1_seen = 0;
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);

  bp_print_string("=== ctxtsw smoke test ===\n");
  ctxtsw_to_1();

  if (t1_seen != 1) {
    bp_print_string("[BSG-FAIL] thread 1 did not resume thread 0\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] ctxtsw smoke test completed\n");
  bp_finish(0);
  return 0;
}
