/* Exercise every set in the two-bank 16 KiB L2 through dirty eviction and
 * refill.  This is a correctness gate for capacity experiments, not a
 * performance benchmark or proof that Linux can boot with a configuration.
 */
#include <stdint.h>

#include "bp_utils.h"

enum { lines_per_region = 128, words_per_line = 8 };

struct cache_line {
  uint64_t word[words_per_line];
};

/* Keep the scratch footprint out of BSS.  Clearing three 8 KiB arrays before
 * main obscures this test's phase boundaries and needlessly dominates traced
 * simulation.  These aligned addresses are well beyond the test ELF and
 * remain inside the platform's 128 MiB DRAM window. */
#define REGION_A ((volatile struct cache_line *)(uintptr_t)UINT64_C(0x80100000))
#define REGION_B ((volatile struct cache_line *)(uintptr_t)UINT64_C(0x80102000))
#define REGION_C ((volatile struct cache_line *)(uintptr_t)UINT64_C(0x80104000))

static uint64_t expected(unsigned region, unsigned line, unsigned word,
                         unsigned epoch)
{
  return UINT64_C(0x6c325f696e746567)
         ^ ((uint64_t)region << 56)
         ^ ((uint64_t)epoch << 48)
         ^ ((uint64_t)line << 8)
         ^ word;
}

static void fill(volatile struct cache_line *region, unsigned region_id,
                 unsigned epoch)
{
  for (unsigned line = 0; line < lines_per_region; ++line)
    region[line].word[0] = expected(region_id, line, 0, epoch);
}

static int verify(volatile const struct cache_line *region,
                  unsigned region_id, unsigned epoch)
{
  for (unsigned line = 0; line < lines_per_region; ++line)
    if (region[line].word[0] != expected(region_id, line, 0, epoch))
      return 0;
  return 1;
}

static void __attribute__((noreturn)) fail(char *phase)
{
  bp_print_string("[BSG-FAIL] L2 capacity integrity: ");
  bp_print_string(phase);
  bp_print_string("\n");
  bp_finish(1);
  for (;;) ;
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif

  /* Two regions occupy all 256 lines of a 2-bank, 2-way, 64-set L2.  The
   * third region then forces dirty victims through the complete set range. */
  bp_print_string("L2-CAPACITY begin\n");
  fill(REGION_A, 1, 1);
  fill(REGION_B, 2, 1);
  if (!verify(REGION_A, 1, 1) || !verify(REGION_B, 2, 1))
    fail("initial full-capacity readback");
  bp_print_string("L2-CAPACITY initial-full readback\n");

  fill(REGION_C, 3, 1);
  if (!verify(REGION_C, 3, 1))
    fail("eviction-region readback");
  if (!verify(REGION_A, 1, 1) || !verify(REGION_B, 2, 1))
    fail("dirty refill after over-capacity sweep");
  bp_print_string("L2-CAPACITY dirty-refill readback\n");

  fill(REGION_A, 1, 2);
  fill(REGION_C, 3, 2);
  if (!verify(REGION_A, 1, 2) || !verify(REGION_B, 2, 1)
      || !verify(REGION_C, 3, 2))
    fail("second-epoch alias check");

  bp_print_string("[BSG-PASS] L2 capacity integrity\n");
  bp_finish(0);
  return 0;
}
