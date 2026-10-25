/* Exercise the absent-feature CSR probes used by OpenSBI before Linux entry.
 * Unsupported optional CSRs must trap so firmware does not advertise them.
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
  const uint64_t unexpected =
    probe_pmpcfg0() | probe_pmpcfg2()
    | probe_pmpaddr0() | probe_pmpaddr1()
    | probe_pmpaddr2() | probe_pmpaddr3()
    | probe_mhpmcounter3() | probe_mhpmevent3();

  if (unexpected != 0) {
    bp_print_string("[BSG-FAIL] OpenSBI absent CSR probe read nonzero\n");
    bp_hprint_uint64(unexpected);
    bp_finish(1);
    return 1;
  }

  __asm__ volatile("la t0, machine_trap\ncsrw mtvec, t0\n"
                   : : : "t0", "memory");
  EXPECT_ILLEGAL_CSR(0x14d);
  EXPECT_ILLEGAL_CSR(0x30a);
  EXPECT_ILLEGAL_CSR(0x30c);
  EXPECT_ILLEGAL_CSR(0x321);
  EXPECT_ILLEGAL_CSR(0xda0);
  EXPECT_ILLEGAL_CSR(0xfb0);

  bp_print_string("[BSG-PASS] OpenSBI absent CSR probes trap\n");
  bp_finish(0);
  return 0;
}
