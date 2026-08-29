/**
 * FPGA FP execution smoke test.
 *
 * Reproduces the SDK startup's back-to-back FP register clear without using a
 * context switch. Raw C/D/E/F markers localize failures before libc output is
 * available:
 *   C: entered main
 *   D: enabled mstatus.FS
 *   E: wrote all 32 FP registers
 *   F: read f31 back as zero
 */

#include <stdint.h>

#include "bp_utils.h"

static inline void raw_marker(char marker) {
  *(volatile uint8_t *)(uintptr_t)0x00101000 = (uint8_t)marker;
}

int main(void) {
  uint64_t value;

  raw_marker('C');
  __asm__ volatile("csrs mstatus, %0" : : "r"(3ULL << 13) : "memory");
  __asm__ volatile("nop; nop; nop; nop" ::: "memory");
  raw_marker('D');

  __asm__ volatile(
    "fmv.d.x f0,  zero\n"
    "fmv.d.x f1,  zero\n"
    "fmv.d.x f2,  zero\n"
    "fmv.d.x f3,  zero\n"
    "fmv.d.x f4,  zero\n"
    "fmv.d.x f5,  zero\n"
    "fmv.d.x f6,  zero\n"
    "fmv.d.x f7,  zero\n"
    "fmv.d.x f8,  zero\n"
    "fmv.d.x f9,  zero\n"
    "fmv.d.x f10, zero\n"
    "fmv.d.x f11, zero\n"
    "fmv.d.x f12, zero\n"
    "fmv.d.x f13, zero\n"
    "fmv.d.x f14, zero\n"
    "fmv.d.x f15, zero\n"
    "fmv.d.x f16, zero\n"
    "fmv.d.x f17, zero\n"
    "fmv.d.x f18, zero\n"
    "fmv.d.x f19, zero\n"
    "fmv.d.x f20, zero\n"
    "fmv.d.x f21, zero\n"
    "fmv.d.x f22, zero\n"
    "fmv.d.x f23, zero\n"
    "fmv.d.x f24, zero\n"
    "fmv.d.x f25, zero\n"
    "fmv.d.x f26, zero\n"
    "fmv.d.x f27, zero\n"
    "fmv.d.x f28, zero\n"
    "fmv.d.x f29, zero\n"
    "fmv.d.x f30, zero\n"
    "fmv.d.x f31, zero\n"
    ::: "memory");

  raw_marker('E');
  __asm__ volatile("fmv.x.d %0, f31" : "=r"(value));
  if (value != 0) {
    bp_print_string("[BSG-FAIL] FPGA FP register readback was nonzero\n");
    bp_finish(1);
    return 1;
  }

  raw_marker('F');
  bp_print_string("[BSG-PASS] FPGA FP execution smoke completed\n");
  bp_finish(0);
  return 0;
}
