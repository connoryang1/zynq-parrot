/**
 * mt_ctxtsw_fpga_stage_test.c
 *
 * Board-visible staged probe for resident and nonresident context switching.
 * Keep each stage to one round trip and print at every boundary so a physical
 * FPGA stall can be localized without an internal waveform.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256
static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static volatile uint64_t t1_seen;
static volatile uint64_t t2_seen;

static inline void ctxtsw(unsigned int target) {
  if (target == 0)
    __asm__ volatile("csrwi 0x081, 0" ::: "memory");
  else if (target == 1)
    __asm__ volatile("csrwi 0x081, 1" ::: "memory");
  else
    __asm__ volatile("csrwi 0x081, 2" ::: "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  bp_print_string("[STAGE] resident context 1 entered\n");
  t1_seen = 1;
  ctxtsw(0);
  for (;;)
    ;
}

void __attribute__((noinline, noreturn)) t2_entry(void) {
  bp_print_string("[STAGE] nonresident context 2 entered\n");
  t2_seen = 1;
  ctxtsw(0);
  for (;;)
    ;
}

int main(void) {
  t1_seen = 0;
  t2_seen = 0;

  bp_print_string("[STAGE] main entered\n");
  bp_print_string("[STAGE] before seed resident context 1\n");
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  bp_print_string("[STAGE] after seed resident context 1\n");
  bp_print_string("[STAGE] before seed nonresident context 2\n");
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);
  bp_print_string("[STAGE] after seed nonresident context 2\n");

  bp_print_string("[STAGE] before resident 0->1->0\n");
  ctxtsw(1);
  bp_print_string("[STAGE] after resident 0->1->0\n");

  if (t1_seen != 1) {
    bp_print_string("[BSG-FAIL] resident context did not run\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[STAGE] before nonresident 0->2->0\n");
  ctxtsw(2);
  bp_print_string("[STAGE] after nonresident 0->2->0\n");

  if (t2_seen != 1) {
    bp_print_string("[BSG-FAIL] nonresident context did not run\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] FPGA staged resident/nonresident probe\n");
  bp_finish(0);
  return 0;
}
