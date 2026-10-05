/* Verify that satp exposes exactly the ASID bits implemented by the TLB.
 * The maintained BlackParrot configurations implement one ASID bit.  Linux
 * uses this write/read probe at boot before choosing its ASID allocator.
 */

#include <stdint.h>
#include "bp_utils.h"

#define SATP_MODE_SV39 (UINT64_C(8) << 60)
#define SATP_ASID_SHIFT 44
#define SATP_PPN UINT64_C(0x12345)

static uint64_t probe_satp(uint64_t value)
{
  uint64_t result;
  __asm__ volatile("csrw satp, %1\n\tcsrr %0, satp"
                   : "=r"(result) : "r"(value) : "memory");
  return result;
}

int main(void)
{
  const uint64_t all_asids = probe_satp(
    SATP_MODE_SV39 | (UINT64_C(0xffff) << SATP_ASID_SHIFT) | SATP_PPN);
  const uint64_t unsupported_bit = probe_satp(
    SATP_MODE_SV39 | (UINT64_C(2) << SATP_ASID_SHIFT) | SATP_PPN);
  __asm__ volatile("csrw satp, zero" ::: "memory");

  const uint64_t expected_low_bit =
    SATP_MODE_SV39 | (UINT64_C(1) << SATP_ASID_SHIFT) | SATP_PPN;
  const uint64_t expected_no_asid = SATP_MODE_SV39 | SATP_PPN;
  if (all_asids == expected_low_bit && unsupported_bit == expected_no_asid) {
    bp_print_string("[BSG-PASS] satp ASID WARL width matches one-bit TLB tag\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] satp ASID WARL width\n");
  bp_hprint_uint64(all_asids);
  bp_hprint_uint64(unsupported_bit);
  bp_finish(1);
  return 1;
}
