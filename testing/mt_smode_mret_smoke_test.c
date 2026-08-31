/*
 * Minimal M-mode to S-mode handoff smoke test.
 *
 * This intentionally leaves address translation disabled.  It is the first
 * discriminating gate for the Linux boot regression: a failure here is a
 * generic privilege-transition problem, whereas a pass moves investigation
 * to Sv39 and the Linux early-entry sequence.
 */

#include <stdint.h>
#include "bp_utils.h"

#define MSTATUS_MPP_MASK (3ULL << 11)
#define MSTATUS_MPP_S    (1ULL << 11)

volatile uint64_t trap_mcause;

void __attribute__((noinline, noreturn)) machine_recovery(void)
{
  bp_print_string("[BSG-FAIL] M-to-S handoff trapped; mcause=");
  bp_hprint_uint64(trap_mcause);
  bp_print_string("\n");
  bp_finish(1);
  while (1) { }
}

void __attribute__((naked, aligned(4))) machine_trap_entry(void)
{
  __asm__ volatile(
      "csrr t0, mcause\n\t"
      "la t1, trap_mcause\n\t"
      "sd t0, 0(t1)\n\t"
      "csrr t0, mstatus\n\t"
      "li t1, 0x1800\n\t"
      "or t0, t0, t1\n\t"
      "csrw mstatus, t0\n\t"
      "la t0, machine_recovery\n\t"
      "csrw mepc, t0\n\t"
      "mret\n\t");
}

void __attribute__((noinline, noreturn)) supervisor_entry(void)
{
  bp_print_string("[BSG-PASS] M-to-S handoff completed\n");
  bp_finish(0);
  while (1) { }
}

int main(void)
{
  uint64_t status;

  __asm__ volatile("csrw mtvec, %0" : : "r"((uintptr_t)machine_trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"((uintptr_t)supervisor_entry) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
