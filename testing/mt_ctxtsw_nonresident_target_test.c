/**
 * mt_ctxtsw_nonresident_target_test.c
 *
 * Negative probe for resident-context-map plumbing. Build/run with
 * NUM_THREADS=2 NUM_CONTEXTS=4. Context IDs 0/1 are resident hardware slots;
 * context ID 2 is logical-only until the context cache save/restore FSM exists.
 *
 * Expected behavior today: simulator stops in RTL with
 * "Nonresident context switch target 2 is not implemented yet".
 */

#include "bp_utils.h"

int main(void) {
  bp_print_string("=== Nonresident Context-Switch Target Test ===\n");
  bp_print_string("Attempting csrwi 0x081,2 with only two resident threads.\n");

  __asm__ volatile("csrwi 0x081, 2" ::: "memory");

  bp_print_string("[BSG-FAIL] nonresident ctxtsw unexpectedly continued\n");
  bp_finish(1);
  return 1;
}
