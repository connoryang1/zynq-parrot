/**
 * Minimal SATP-write followed by SFENCE.VMA liveness test.
 *
 * Execution remains in M-mode, so translation is not enabled.  The test only
 * exercises the CSR redirect followed by the frontend/backend TLB fence path.
 */

#include <stdint.h>
#include "bp_utils.h"

#define SV39_SATP_MODE (8ULL << 60)
#define PAGE_WORDS 512

static uint64_t root_page_table[PAGE_WORDS] __attribute__((aligned(4096)));

int main(void) {
  uint64_t satp = SV39_SATP_MODE | ((uint64_t)root_page_table >> 12);

  bp_print_string("[STAGE] before SATP write\n");
  __asm__ volatile("csrw satp, %0" : : "r"(satp) : "memory");
  bp_print_string("[STAGE] after SATP write\n");
  __asm__ volatile("sfence.vma x0, x0" : : : "memory");
  bp_print_string("[STAGE] after SFENCE.VMA\n");

  bp_print_string("[BSG-PASS] SATP plus SFENCE.VMA completed\n");
  bp_finish(0);
  return 0;
}
