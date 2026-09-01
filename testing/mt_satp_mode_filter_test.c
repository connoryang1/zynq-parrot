/**
 * RISC-V SATP mode acceptance test.
 *
 * BlackParrot implements Sv39 only.  Per the privileged ISA, an attempted
 * write with an unsupported MODE must leave SATP unchanged as a whole.  Linux
 * uses precisely that write/readback contract to fall back from Sv57 and Sv48
 * to Sv39 during early page-table setup.
 */

#include <stdint.h>

#include "bp_utils.h"

#define SATP_MODE_BARE  (0ULL << 60)
#define SATP_MODE_SV39  (8ULL << 60)
#define SATP_MODE_SV48  (9ULL << 60)
#define SATP_MODE_SV57  (10ULL << 60)
#define PAGE_WORDS 512

static uint64_t root_page_table[PAGE_WORDS] __attribute__((aligned(4096)));

static inline void write_satp(uint64_t value) {
  __asm__ volatile("csrw satp, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_satp(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, satp" : "=r"(value));
  return value;
}

int main(void) {
  const uint64_t sv39 = SATP_MODE_SV39 | ((uint64_t)root_page_table >> 12);
  uint64_t after_sv48;
  uint64_t after_sv57;
  uint64_t after_sv39;

  write_satp(SATP_MODE_BARE);
  write_satp(SATP_MODE_SV48 | 0x12345ULL);
  after_sv48 = read_satp();
  write_satp(SATP_MODE_SV57 | 0x23456ULL);
  after_sv57 = read_satp();
  write_satp(sv39);
  after_sv39 = read_satp();

  bp_print_string("=== SATP Mode Filter Test ===\n");
  bp_print_string("after Sv48: ");
  bp_hprint_uint64(after_sv48);
  bp_print_string("\nafter Sv57: ");
  bp_hprint_uint64(after_sv57);
  bp_print_string("\nafter Sv39: ");
  bp_hprint_uint64(after_sv39);
  bp_print_string("\n");

  if ((after_sv48 == SATP_MODE_BARE)
      && (after_sv57 == SATP_MODE_BARE)
      && (after_sv39 == sv39)) {
    bp_print_string("[BSG-PASS] unsupported SATP modes preserve prior state\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] unsupported SATP mode was accepted\n");
    bp_finish(1);
  }
  return 0;
}
