/* Check that a translated advisory reply cannot override newer dirty L2 data.
 * The first phase places 0x222 in DRAM. The second flushes 0x333 from L1 to
 * L2 before issuing a translated prefetch.r hint.
 */
#include <stdint.h>

#include "bp_prefetch.h"
#include "bp_utils.h"

static volatile uint64_t target __attribute__((aligned(4096))) = 0x111;
static volatile struct {
  uint64_t pad[8];
  uint64_t enable;
} control __attribute__((aligned(4096))) = {.enable = 1};

static void __attribute__((noreturn)) fail(const char *reason)
{
  bp_print_string("[BSG-FAIL] translated preview dirty L2: ");
  bp_print_string(reason);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

static void evict_to_dram(volatile uint64_t *lines)
{
  volatile uint64_t sum = 0;
  for (unsigned i = 0; i < 32; ++i)
    sum += lines[i * 512];
  (void)sum;
}

static void wait_for_preview(void)
{
  uint64_t start, now;
  __asm__ volatile("rdcycle %0" : "=r"(start));
  do {
    __asm__ volatile("rdcycle %0" : "=r"(now));
  } while (now - start < 3000);
}

int main(void)
{
  volatile uint64_t dram_eviction[32 * 512] __attribute__((aligned(4096)));
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif

  target = 0x222;
  evict_to_dram(dram_eviction);
  if (target != 0x222)
    fail("ordinary DRAM writeback control");
  for (unsigned i = 0; i < 1024; ++i)
    __asm__ volatile("nop" : : : "memory");

  target = 0x333;
  /* BlackParrot's custom CMO flush-all (imm=2, funct3=7) writes dirty L1
   * lines back to the L2 and invalidates L1 without evicting the L2 set. */
  __asm__ volatile(".word 0x0020700f" : : : "memory");
  if (control.enable) {
    __asm__ volatile("csrw 0x805, %0" : : "r"(2UL) : "memory");
    bp_prefetch_r(&target);
    wait_for_preview();
  }
  if (target == 0x222)
    fail("stale translated reply over dirty L2");
  if (target != 0x333)
    fail("unexpected value after L1 eviction");

  bp_print_string("[BSG-PASS] translated preview dirty L2 coherency\n");
  bp_finish(0);
  return 0;
}
