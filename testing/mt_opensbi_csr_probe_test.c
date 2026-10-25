/* Exercise the absent-feature CSR probes used by OpenSBI before Linux entry.
 * This control restores the pre-6a illegal-read behavior for every probe.
 */

#include <stdint.h>
#include "bp_utils.h"

static volatile uint64_t trap_seen;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_pc;
static volatile uint64_t expected_trap_pc;

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

#define EXPECT_ILLEGAL_CSR(csr)                                              \
  do {                                                                       \
    trap_seen = trap_cause = trap_pc = expected_trap_pc = 0;                  \
    __asm__ volatile(                                                         \
      "la t0, 1f\n"                                                          \
      "la t1, expected_trap_pc\n"                                            \
      "sd t0, 0(t1)\n"                                                        \
      "1: csrr t0, " #csr "\n"                                                \
      : : : "t0", "t1", "memory");                                           \
    if (trap_seen != 1 || trap_cause != 2 || trap_pc != expected_trap_pc) {  \
      bp_print_string("[BSG-FAIL] optional CSR did not trap: " #csr "\n");   \
      bp_hprint_uint64(trap_seen);                                            \
      bp_hprint_uint64(trap_cause);                                           \
      bp_hprint_uint64(trap_pc);                                              \
      bp_hprint_uint64(expected_trap_pc);                                     \
      bp_finish(1);                                                           \
      return 1;                                                               \
    }                                                                        \
  } while (0)

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  /* The simulator CRT enters through debug mode; OpenSBI probes in M-mode. */
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
  __asm__ volatile("la t0, machine_trap\ncsrw mtvec, t0\n"
                   : : : "t0", "memory");
  EXPECT_ILLEGAL_CSR(0x3a0);
  EXPECT_ILLEGAL_CSR(0x3a2);
  EXPECT_ILLEGAL_CSR(0x3b0);
  EXPECT_ILLEGAL_CSR(0x3b1);
  EXPECT_ILLEGAL_CSR(0x3b2);
  EXPECT_ILLEGAL_CSR(0x3b3);
  EXPECT_ILLEGAL_CSR(0xb03);
  EXPECT_ILLEGAL_CSR(0x323);
  EXPECT_ILLEGAL_CSR(0x14d);
  EXPECT_ILLEGAL_CSR(0x30a);
  EXPECT_ILLEGAL_CSR(0x30c);
  EXPECT_ILLEGAL_CSR(0x321);
  EXPECT_ILLEGAL_CSR(0xda0);
  EXPECT_ILLEGAL_CSR(0xfb0);

  bp_print_string("[BSG-PASS] OpenSBI legacy absent CSR probes trap\n");
  bp_finish(0);
  return 0;
}
