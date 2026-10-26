/* Check that a physical preview cannot return an older DRAM copy of a dirty
 * D-cache line after the dirty line is evicted. The control phase first proves
 * the same-set eviction and ordinary writeback path without a hint.
 */
#include <stdint.h>

#include "bp_utils.h"

static volatile uint64_t target __attribute__((aligned(4096))) = 0x111;
/* Keep the host-patched enable word one cache set away from target. Reading
 * the control immediately before the hint must not itself evict the dirty
 * target from set zero. */
static volatile struct {
  uint64_t pad[8];
  uint64_t enable;
} control __attribute__((aligned(4096))) = {.enable = 1};
static void __attribute__((noreturn)) fail(char *reason)
{
  bp_print_string("[BSG-FAIL] physical preview dirty line: ");
  bp_print_string(reason);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

static void evict_set(volatile uint64_t *eviction, unsigned first)
{
  volatile uint64_t sum = 0;
  for (unsigned i = first; i < first + 16; ++i) {
    uint64_t value;
    /* The stack region needs no initialization: the load creates the cache
     * conflict, and its old contents are irrelevant to this test. */
    __asm__ volatile("ld %0, 0(%1)" : "=r"(value)
                     : "r"(&eviction[i * 512]) : "memory");
    sum += value;
  }
  (void)sum;
}

static void wait_for_preview(void)
{
  /* Leave a bounded window for the detached request to return. The traced
   * run must independently show publication before the eviction loads. */
  uint64_t start, now;
  __asm__ volatile("rdcycle %0" : "=r"(start));
  do {
    __asm__ volatile("rdcycle %0" : "=r"(now));
  } while (now - start < 3000);
}

int main(void)
{
  /* Local storage avoids both a large .bss clear and a large loaded NBF.
   * All 32 lines share the target's D-cache set (64 sets x 64 bytes). */
  volatile uint64_t eviction[32 * 512] __attribute__((aligned(4096)));
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif

  target = 0x222;
  evict_set(eviction, 0);
  if (target != 0x222)
    fail("ordinary eviction/writeback control");

  /* The critical word can retire before the ordinary 64-byte fill tail.
   * Wait for that authoritative request to leave the UCE before issuing an
   * advisory hint to the same physical line. */
  for (unsigned i = 0; i < 1024; ++i)
    __asm__ volatile("nop" : : : "memory");

  target = 0x333;
  if (control.enable) {
    __asm__ volatile("csrw 0x805, %0" : : "r"(2UL) : "memory");
    __asm__ volatile("csrw 0x9c0, %0" : : "r"((uintptr_t)&target) : "memory");
    wait_for_preview();
  }
  evict_set(eviction, 16);
  if (target == 0x222)
    fail("stale prefetch value after dirty eviction");
  if (target != 0x333)
    fail("unexpected value after dirty eviction");

  bp_print_string("[BSG-PASS] physical preview dirty line coherency\n");
  bp_finish(0);
  return 0;
}
