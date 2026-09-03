/*
 * Regression for OpenSBI's unsupported machine-HPM capability probes.
 *
 * BlackParrot does not implement programmable hardware performance monitors,
 * but their standard M-mode CSRs must remain legal. They are WARL: writes are
 * ignored and reads return zero, accurately reporting no optional counters.
 */

#include "bp_utils.h"

static inline void write_mhpmcounter3(uint64_t value) {
  __asm__ volatile("csrw 0xb03, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_mhpmcounter3(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0xb03" : "=r"(value));
  return value;
}

static inline void write_mhpmcounter31(uint64_t value) {
  __asm__ volatile("csrw 0xb1f, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_mhpmcounter31(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0xb1f" : "=r"(value));
  return value;
}

static inline void write_mhpmevent3(uint64_t value) {
  __asm__ volatile("csrw 0x323, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_mhpmevent3(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x323" : "=r"(value));
  return value;
}

static inline void write_mhpmevent31(uint64_t value) {
  __asm__ volatile("csrw 0x33f, %0" : : "r"(value) : "memory");
}

static inline uint64_t read_mhpmevent31(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0x33f" : "=r"(value));
  return value;
}

int main(void) {
  write_mhpmcounter3(~0ull);
  write_mhpmcounter31(1);
  write_mhpmevent3(~0ull);
  write_mhpmevent31(1);

  if (read_mhpmcounter3() || read_mhpmcounter31()
      || read_mhpmevent3() || read_mhpmevent31()) {
    bp_print_string("\n[BSG-FAIL] unsupported HPM CSR retained state\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("\n[BSG-PASS] unsupported HPM CSRs are legal zero WARL\n");
  bp_finish(0);
  return 0;
}
