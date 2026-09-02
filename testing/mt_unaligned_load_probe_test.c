/*
 * Minimal unaligned 64-bit load probe for Linux boot triage.
 *
 * Linux's check_unaligned_access() first calls
 * __riscv_copy_words_unaligned() before waiting for jiffies.  That helper
 * issues misaligned LD instructions.  A conforming implementation may either
 * complete the load in hardware or raise a load-address-misaligned exception;
 * this test accepts either outcome, but requires forward progress.
 */

#include <stdint.h>
#include "bp_utils.h"

#define CAUSE_LOAD_ADDR_MISALIGNED 4UL

static uint64_t source_words[2] __attribute__((aligned(16), used)) = {
  0x1122334455667788ULL,
  0x99aabbccddeeff00ULL,
};

volatile uint64_t trap_cause;
volatile uint64_t trap_epc;
volatile uint64_t load_value;

/*
 * Keep the first localization points independent of the C console helpers.
 * The FPGA host exposes this byte-wide address as stdout, so these markers
 * tell us whether a failure occurs before the LD, in its trap, or after mret.
 */
static inline void emit_marker(char c) {
  *(volatile uint8_t *)0x00101000UL = (uint8_t)c;
}

/* This direct NBF bypasses the boot ROM's normal debug-to-M-mode dret. */
static inline void leave_debug_to_machine(void) {
  __asm__ volatile(
      "li t0, 3\n"
      "csrw dcsr, t0\n"
      "la t0, 1f\n"
      "csrw dpc, t0\n"
      "dret\n"
      "1:\n"
      : : : "t0", "memory");
}

int unaligned_resume_c(void);

/*
 * A trapping load has no defined destination register.  Resume through a
 * known register-independent shim instead of falling through to the load's
 * compiler-generated dependent store.
 */
void __attribute__((naked, aligned(4))) unaligned_resume(void) {
  __asm__ volatile(
      "li t0, 0x00101000\n"
      "li t1, 'R'\n"
      "sb t1, 0(t0)\n"
      "j unaligned_resume_c\n");
}

void __attribute__((naked, aligned(4))) trap_entry(void) {
  __asm__ volatile(
      ".option push\n"
      ".option norelax\n"
      "li t1, 0x00101000\n"
      "li t2, 'T'\n"
      "sb t2, 0(t1)\n"
      "csrr t0, mcause\n"
      "andi t2, t0, 0xf\n"
      "addi t2, t2, '0'\n"
      "sb t2, 0(t1)\n"
      "li t2, 'C'\n"
      "sb t2, 0(t1)\n"
      "la t1, trap_cause\n"
      "sd t0, 0(t1)\n"
      "li t1, 0x00101000\n"
      "li t2, 'D'\n"
      "sb t2, 0(t1)\n"
      "csrr t0, mepc\n"
      "andi t2, t0, 0xf\n"
      "addi t2, t2, '0'\n"
      "sb t2, 0(t1)\n"
      "li t2, 'E'\n"
      "sb t2, 0(t1)\n"
      "la t1, trap_epc\n"
      "sd t0, 0(t1)\n"
      "li t1, 0x00101000\n"
      "li t2, 'F'\n"
      "sb t2, 0(t1)\n"
      "la t0, unaligned_resume\n"
      "csrw mepc, t0\n"
      "li t2, 'G'\n"
      "sb t2, 0(t1)\n"
      ".option pop\n"
      "mret\n");
}

int unaligned_resume_c(void) {
  emit_marker('R');

  bp_print_string("=== Unaligned Load Progress Probe ===\ntrap cause: ");
  bp_hprint_uint64(trap_cause);
  bp_print_string("\ntrap epc:   ");
  bp_hprint_uint64(trap_epc);
  bp_print_string("\nload value: ");
  bp_hprint_uint64(load_value);
  bp_print_string("\n");

  if (trap_cause == 0) {
    emit_marker('P');
    bp_print_string("[BSG-PASS] hardware completed unaligned LD\n");
    bp_finish(0);
  } else if (trap_cause == CAUSE_LOAD_ADDR_MISALIGNED) {
    emit_marker('P');
    bp_print_string("[BSG-PASS] unaligned LD trapped and recovered\n");
    bp_finish(0);
  } else {
    emit_marker('F');
    bp_print_string("[BSG-FAIL] unexpected unaligned-load trap cause\n");
    bp_finish(1);
  }
  return 0;
}

int main(void) {
  uintptr_t mtvec = (uintptr_t)trap_entry;

  leave_debug_to_machine();
  __asm__ volatile("csrw mtvec, %0" : : "r"(mtvec) : "memory");
  emit_marker('U');
  __asm__ volatile(
      "la t1, source_words\n"
      "addi t1, t1, 1\n"
      "ld t0, 0(t1)\n"
      "sd t0, %0\n"
      : "=m"(load_value)
      :
      : "t0", "t1", "memory");
  return unaligned_resume_c();
}
