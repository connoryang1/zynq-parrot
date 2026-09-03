/*
 * Regression for OpenSBI's first PMP capability probe.
 *
 * BlackParrot has no PMP enforcement, but OpenSBI must be able to execute its
 * PMP CSR probes without taking the illegal-instruction/debug path.  Legal
 * hardwired-zero WARL CSRs make the firmware correctly detect zero usable PMP
 * entries without advertising protection hardware that does not exist.
 */

#include "bp_utils.h"

static inline void write_pmpcfg0(uint64_t value) {
  __asm__ volatile("csrw 0x3a0, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_pmpcfg0(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x3a0" : "=r"(value));
  return value;
}

static inline void write_pmpaddr0(uint64_t value) {
  __asm__ volatile("csrw 0x3b0, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_pmpaddr0(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x3b0" : "=r"(value));
  return value;
}

int main(void) {
  const uint64_t pmpaddr_write = 0x12345;
  const uint64_t pmpcfg_write = 0x8f;
  uint64_t cfg;
  uint64_t addr;

  /* OpenSBI's initial clear, using the fixed encoding so this test does not
   * rely on the toolchain's optional PMP CSR mnemonic support. */
  __asm__ volatile(".word 0x3a001073" : : : "memory");

  write_pmpaddr0(pmpaddr_write);
  write_pmpcfg0(pmpcfg_write);
  cfg = read_pmpcfg0();
  addr = read_pmpaddr0();
  if ((cfg == 0) && (addr == 0)) {
    bp_print_string("\n[BSG-PASS] PMP CSRs are legal hardwired-zero WARL\n");
    bp_finish(0);
  } else {
    bp_print_string("\n[BSG-FAIL] PMP CSR exposed unenforced state\n");
    bp_finish(1);
  }

  return 0;
}
