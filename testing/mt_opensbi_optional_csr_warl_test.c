/*
 * Regression for OpenSBI's optional privileged-ISA capability probes.
 *
 * BlackParrot implements none of these optional extensions.  Their CSRs are
 * therefore legal hardwired-zero WARL registers: reads report no capability
 * and writes, where attempted, are ignored without entering the trap path.
 */

#include "bp_utils.h"

#define DEFINE_CSR_READ(name, address) \
  static inline uint64_t name(void) { \
    uint64_t value; \
    __asm__ volatile("csrr %0, " address : "=r"(value)); \
    return value; \
  }

#define DEFINE_CSR_WRITE(name, address) \
  static inline void name(uint64_t value) { \
    __asm__ volatile("csrw " address ", %0" : : "r"(value) : "memory"); \
  }

DEFINE_CSR_READ(read_menvcfg, "0x30a")
DEFINE_CSR_READ(read_mstateen0, "0x30c")
DEFINE_CSR_READ(read_mcyclecfg, "0x321")
DEFINE_CSR_READ(read_scountovf, "0xda0")
DEFINE_CSR_READ(read_mtopi, "0xfb0")
DEFINE_CSR_READ(read_stimecmp, "0x14d")
DEFINE_CSR_WRITE(write_menvcfg, "0x30a")
DEFINE_CSR_WRITE(write_mstateen0, "0x30c")
DEFINE_CSR_WRITE(write_mcyclecfg, "0x321")
DEFINE_CSR_WRITE(write_stimecmp, "0x14d")

int main(void) {
  write_menvcfg(~0ull);
  write_mstateen0(~0ull);
  write_mcyclecfg(~0ull);
  write_stimecmp(~0ull);

  if (read_menvcfg() || read_mstateen0() || read_mcyclecfg()
      || read_scountovf() || read_mtopi() || read_stimecmp()) {
    bp_print_string("\n[BSG-FAIL] optional OpenSBI probe CSR retained state\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("\n[BSG-PASS] optional OpenSBI probe CSRs are legal zero WARL\n");
  bp_finish(0);
  return 0;
}
