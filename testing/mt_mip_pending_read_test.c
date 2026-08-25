/**
 * Read MIP with MTIP asserted while machine interrupts remain disabled.
 *
 * This isolates the pending-CSR datapath from trap entry, mtvec, and mret.
 */

#include <stdint.h>
#include "bp_utils.h"

#define MTIME_ADDR    0x0030bff8UL
#define MTIMECMP_ADDR 0x00304000UL
#define MIP_MTIP      (1UL << 7)
#define MSTATUS_MIE   (1UL << 3)

static volatile uint64_t *const mtime = (uint64_t *)MTIME_ADDR;
static volatile uint64_t *const mtimecmp = (uint64_t *)MTIMECMP_ADDR;

int main(void) {
  uint64_t pending;
  uint64_t target;

  __asm__ volatile("csrc mstatus, %0" : : "r"(MSTATUS_MIE) : "memory");
  target = *mtime + 4096;
  *mtimecmp = target;
  while (*mtime < target) {
    __asm__ volatile("nop");
  }

  __asm__ volatile("csrr %0, mip" : "=r"(pending));
  *mtimecmp = UINT64_MAX;

  bp_print_string("=== Pending MIP Read Test ===\n");
  bp_print_string("mip:          ");
  bp_hprint_uint64(pending);
  bp_print_string("\n");

  if ((pending & MIP_MTIP) != 0) {
    bp_print_string("[BSG-PASS] pending MTIP is readable with interrupts disabled\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] pending MTIP was not observed\n");
    bp_finish(1);
  }

  return 0;
}
