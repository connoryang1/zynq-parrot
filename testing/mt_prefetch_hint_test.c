/* Check nonfaulting prefetch hints, encoded offsets, and ordinary load data.
 * The transaction-level UCE test establishes outstanding-request accounting;
 * this program checks the instruction path and dirty data through the core.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "bp_prefetch.h"

struct line { uint64_t word[8]; };
#define WORDS(n) {{(n)+0, (n)+1, (n)+2, (n)+3, (n)+4, (n)+5, (n)+6, (n)+7}}
static const volatile struct line cold[8] __attribute__((aligned(4096), used)) = {
  WORDS(0x100), WORDS(0x200), WORDS(0x300), WORDS(0x400),
  WORDS(0x500), WORDS(0x600), WORDS(0x700), WORDS(0x800)
};
static volatile struct line dirty __attribute__((aligned(64), used));

static void __attribute__((used, noinline, noreturn)) fail(void)
{
  bp_print_string("[BSG-FAIL] prefetch hint data or unexpected trap\n");
  bp_finish(1);
  for (;;) ;
}

static void __attribute__((naked, aligned(4))) trap(void)
{
  __asm__ volatile("la t0, fail\ncsrw mepc, t0\nmret\n");
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:"
    : : : "t0", "memory");
#endif
  __asm__ volatile("csrw mtvec, %0" : : "r"((uintptr_t)trap) : "memory");
  // None of these hints may raise an exception or perform an MMIO read.
  bp_prefetch_r((const void *)UINT64_C(0));
  bp_prefetch_r((const void *)UINT64_C(0x1000));
  bp_prefetch_r((const void *)UINT64_C(0x8000000000000000));

  uint64_t actual;
  __asm__ volatile("ori %0, %1, 33" : "=r"(actual) : "r"(UINT64_C(0x1200)));
  if (actual != 0x1221) fail();

  // Low immediate bits select the hint; effective offsets are +32 and -32.
  __asm__ volatile("ori zero, %0, 33\nori zero, %1, -31"
    : : "r"(&cold[0].word[0]), "r"(&cold[1].word[4]) : "memory");
  for (unsigned i = 0; i < 8; ++i) {
    // Word offsets exercise alignment and the lower-level response identity.
    bp_prefetch_r(&cold[i].word[i]);
    for (unsigned j = 0; j < 8; ++j)
      if (cold[i].word[j] != (i + 1) * 0x100 + j) fail();
  }

  for (unsigned i = 0; i < 8; ++i) dirty.word[i] = 0x9870 + i;
  bp_prefetch_r(&dirty.word[3]);
  dirty.word[3] = 0xabcd;
  __asm__ volatile("fence rw, rw" : : : "memory");
  for (unsigned i = 0; i < 8; ++i)
    if (dirty.word[i] != (i == 3 ? 0xabcd : 0x9870 + i)) fail();

  bp_print_string("[BSG-PASS] nonfaulting prefetch hints\n");
  bp_finish(0);
  return 0;
}
