/* Check that a privileged cancel drains detached hints and clears advisory
 * data before software releases a page that was named by a physical hint.
 */
#include <stdint.h>

#include "bp_prefetch.h"
#include "bp_utils.h"

static const volatile uint64_t translated_page[16]
  __attribute__((aligned(4096), used)) = {
    [0] = 0x5a5, [8] = 0x988
  };
static const volatile uint64_t physical_target[4][8]
  __attribute__((aligned(4096), used)) = {
    {0x711}, {0x722}, {0x733}, {0x744}
  };

static void __attribute__((noreturn)) fail(const char *reason)
{
  bp_print_string("[BSG-FAIL] preview quiesce: ");
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

static inline uint64_t preview_idle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0x9c0" : "=r"(value) : : "memory");
  return value & 1;
}

static void wait_for_count(unsigned shift, unsigned count, const char *stage)
{
  for (unsigned i = 0; i < 4096; ++i)
    if (((trace_status() >> shift) & 0xff) >= count)
      return;
  fail(stage);
}

static void cancel_and_wait(void)
{
  physical_hint(0); /* Reserved zero operand cancels queued previews. */
  for (unsigned i = 0; i < 4096; ++i)
    if (preview_idle())
      return;
  fail("issued preview did not drain");
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
  /* Touch a different line of this page to seed its DTLB translation while
   * preserving a cold L1 target line for the later demand-miss check. */
  if (translated_page[8] != 0x988)
    fail("translation warmup data changed");
  bp_prefetch_r(&translated_page[0]);
  wait_for_count(45, 1, "translated hint was not published");
  cancel_and_wait();

  trace_control(3); /* Clear and arm demand-miss counting. */
  for (unsigned i = 0; i < 64; ++i)
    __asm__ volatile("nop" : : : "memory");
  if (translated_page[0] != 0x5a5)
    fail("translated target data changed");
  if (((trace_status() >> 9) & 0x1ff) != 1)
    fail("cancel left an L1 advisory entry live");

  trace_control(2);
  for (unsigned i = 0; i < 4; ++i)
    physical_hint((uint64_t)(uintptr_t)&physical_target[i][0]);
  wait_for_count(37, 1, "physical hint was not issued");
  cancel_and_wait();
  for (unsigned i = 0; i < 4; ++i)
    if (physical_target[i][0] != 0x711 + 0x11 * i)
      fail("physical target data changed");

  bp_print_string("[BSG-PASS] preview cancel drain and advisory invalidation\n");
  bp_finish(0);
  return 0;
}
