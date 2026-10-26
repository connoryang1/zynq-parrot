/* Verify that a privileged physical preview write completes for four DRAM
 * words. The same gate checks that MMIO and out-of-width operands never enter
 * the detached request queue. This runs in bare-metal M mode with identity maps.
 */
#include <stdint.h>

#include "bp_utils.h"

struct line { uint64_t word[8]; };
static const volatile struct line target[4]
  __attribute__((aligned(4096), used)) = {
    {{0x741}}, {{0x742}}, {{0x743}}, {{0x744}}
  };
static const volatile struct line probe
  __attribute__((aligned(64), used)) = {{0x638}};
/* Host patch to zero for an exact-ELF cold-burst control. */
static volatile uint64_t single_before_batch = 1;

static void __attribute__((noreturn)) fail(const char *reason)
{
  bp_print_string("[BSG-FAIL] physical preview CSR: ");
  bp_print_string(reason);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

static inline void trace_control(uint64_t value)
{
  __asm__ volatile("csrw 0x805, %0" : : "r"(value) : "memory");
}

static inline uint64_t trace_status(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0x805" : "=r"(value) : : "memory");
  return value;
}

static inline void physical_hint(uint64_t paddr)
{
  __asm__ volatile("csrw 0x9c0, %0" : : "r"(paddr) : "memory");
}

static uint64_t wait_published(unsigned expected)
{
  for (unsigned i = 0; i < 4096; ++i) {
    uint64_t status = trace_status();
    if (((status >> 45) & 0xff) == expected)
      return status;
  }
  fail("timed out waiting for publications");
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif

  trace_control(2);
  physical_hint(0x00300000);   /* CLINT/MMIO, rejected by PMA. */
  physical_hint(UINT64_MAX);   /* Wider than the physical address port. */
  for (unsigned i = 0; i < 64; ++i)
    __asm__ volatile("nop" : : : "memory");
  uint64_t rejected = trace_status();
  if (((rejected >> 29) & 0xff) || ((rejected >> 37) & 0xff)
      || ((rejected >> 45) & 0xff))
    fail("forbidden address entered the preview queue");

  uint64_t status;
  if (single_before_batch) {
    trace_control(2);
    physical_hint((uint64_t)(uintptr_t)&probe.word[0]);
    status = wait_published(1);
    if (((status >> 29) & 0xff) != 1 || ((status >> 37) & 0xff) != 1
        || probe.word[0] != 0x638)
      fail("single physical hint did not complete");
  }

  trace_control(2);
  for (unsigned i = 0; i < 4; ++i)
    physical_hint((uint64_t)(uintptr_t)&target[i].word[0]);
  status = wait_published(4);
  if (((status >> 29) & 0xff) != 4 || ((status >> 37) & 0xff) != 4)
    fail("four hints were not admitted and issued");

  trace_control(1); /* Count demand misses without clearing the queue. */
  /* The recorder arms at the CSR edge. Keep the first target load outside
   * that edge so all four cold L1 fills are counted. */
  for (unsigned i = 0; i < 64; ++i)
    __asm__ volatile("nop" : : : "memory");
  uint64_t sum = 0;
  for (unsigned i = 0; i < 4; ++i)
    sum += target[i].word[0];
  status = trace_status();
  trace_control(0);
  if (sum != 0x741 + 0x742 + 0x743 + 0x744)
    fail("target data mismatch");
  /* Physical previews warm L2 without supplying the L1 advisory buffer.
   * Four distinct cold L1 lines therefore still require four D-cache fills. */
  if (((status >> 9) & 0x1ff) != 4)
    fail("physical preview unexpectedly supplied an L1 demand");

  bp_print_string("[BSG-PASS] physical preview CSR DRAM and PMA gates\n");
  bp_finish(0);
  return 0;
}
