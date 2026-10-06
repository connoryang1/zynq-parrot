/* Verify a cold machine-mode synchronous trap before any context handoff. */

#include <stdint.h>
#include "bp_utils.h"

static volatile uint64_t trap_seen;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_pc;

static void __attribute__((used, naked, aligned(4))) machine_trap(void)
{
  __asm__ volatile(
    "csrr t0, mcause\n"
    "la t1, trap_cause\n"
    "sd t0, 0(t1)\n"
    "csrr t0, mepc\n"
    "la t1, trap_pc\n"
    "sd t0, 0(t1)\n"
    "addi t0, t0, 4\n"
    "csrw mepc, t0\n"
    "li t0, 1\n"
    "la t1, trap_seen\n"
    "sd t0, 0(t1)\n"
    "mret\n");
}

int main(void)
{
  uintptr_t expected_pc;
#ifndef BP_FPGA_PROGRAM
  /* The minimal simulator CRT enters through debug mode.  Leave it before
   * provoking the exception so ECALL follows the architectural mtvec path,
   * matching the state used by OpenSBI and the FPGA CRT. */
  __asm__ volatile(
    "csrr t0, dcsr\n"
    "ori t0, t0, 3\n"
    "csrw dcsr, t0\n"
    "la t0, 1f\n"
    "csrw dpc, t0\n"
    "dret\n"
    "1:"
    : : : "t0", "memory");
#endif
  __asm__ volatile(
    "la t0, machine_trap\n"
    "csrw mtvec, t0\n"
    "la %0, 1f\n"
    "1: ecall\n"
    : "=r"(expected_pc) : : "t0", "memory");

  if (trap_seen == 1 && trap_cause == 11 && trap_pc == expected_pc) {
    bp_print_string("[BSG-PASS] cold M-mode ECALL trap and return\n");
    bp_finish(0);
  }

  bp_print_string("[BSG-FAIL] cold M-mode ECALL trap and return\n");
  bp_hprint_uint64(trap_seen);
  bp_hprint_uint64(trap_cause);
  bp_hprint_uint64(trap_pc);
  bp_hprint_uint64(expected_pc);
  bp_finish(1);
  return 1;
}
