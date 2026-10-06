/* Exercise the absent-feature CSR probes used by OpenSBI before Linux entry.
 * Unsupported facilities are reported as legal hardwired-zero WARL state.
 */

#include <stdint.h>
#include "bp_utils.h"

#define DEFINE_RW_PROBE(name, csr)                                      \
  static uint64_t probe_##name(void)                                    \
  {                                                                     \
    uint64_t old_value, readback;                                       \
    const uint64_t ones = UINT64_MAX;                                   \
    __asm__ volatile("csrrw %0, " #csr ", %2\n\t"                    \
                     "csrr %1, " #csr                                  \
                     : "=r"(old_value), "=r"(readback)                 \
                     : "r"(ones) : "memory");                          \
    return old_value | readback;                                        \
  }

#define DEFINE_RO_PROBE(name, csr)                                      \
  static uint64_t probe_##name(void)                                    \
  {                                                                     \
    uint64_t value;                                                     \
    __asm__ volatile("csrr %0, " #csr : "=r"(value) : : "memory");    \
    return value;                                                       \
  }

DEFINE_RW_PROBE(pmpcfg0,  0x3a0)
DEFINE_RW_PROBE(pmpcfg2,  0x3a2)
DEFINE_RW_PROBE(pmpaddr0, 0x3b0)
DEFINE_RW_PROBE(pmpaddr1, 0x3b1)
DEFINE_RW_PROBE(pmpaddr2, 0x3b2)
DEFINE_RW_PROBE(pmpaddr3, 0x3b3)
DEFINE_RO_PROBE(mhpmcounter3, 0xb03)
DEFINE_RW_PROBE(mhpmevent3,   0x323)
DEFINE_RW_PROBE(menvcfg,      0x30a)
DEFINE_RW_PROBE(mstateen0,    0x30c)
DEFINE_RW_PROBE(mcyclecfg,    0x321)
DEFINE_RO_PROBE(scountovf,    0xda0)
DEFINE_RO_PROBE(mtopi,        0xfb0)
DEFINE_RW_PROBE(stimecmp,     0x14d)

int main(void)
{
  const uint64_t unexpected =
    probe_pmpcfg0() | probe_pmpcfg2()
    | probe_pmpaddr0() | probe_pmpaddr1()
    | probe_pmpaddr2() | probe_pmpaddr3()
    | probe_mhpmcounter3() | probe_mhpmevent3()
    | probe_menvcfg() | probe_mstateen0() | probe_mcyclecfg()
    | probe_scountovf() | probe_mtopi() | probe_stimecmp();

  if (unexpected == 0) {
    bp_print_string("[BSG-PASS] OpenSBI absent CSR probes read zero\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] OpenSBI absent CSR probe read nonzero\n");
  bp_hprint_uint64(unexpected);
  bp_finish(1);
  return 1;
}
