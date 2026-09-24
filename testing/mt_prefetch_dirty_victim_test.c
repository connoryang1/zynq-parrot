#include <stdint.h>
#include "bp_utils.h"
#include "bp_prefetch.h"

/* Eight-way, 64-set, 64-byte L1D: these nine lines share set 16.
 * Initialized data avoids any dependence on the runtime's BSS zeroing. */
static volatile uint64_t pages[9][512] __attribute__((aligned(4096), used)) = {
  [0][128]=1,[1][128]=2,[2][128]=3,[3][128]=4,[4][128]=5,
  [5][128]=6,[6][128]=7,[7][128]=8,[8][128]=0xfeed9
};

/* No stack accesses or C calls between filling the set and checking it.
 * All eight words in every resident way are dirty. Return one bit per
 * corrupted line, plus bit 8 if the ninth line's initial value is wrong. */
static uint64_t __attribute__((naked, noinline)) exercise(void)
{
  __asm__ volatile(
    "la a1, pages\naddi a1, a1, 1024\nmv a2, a1\n"
    "li a3, 8\nli a4, 0x5a00\nli a5, 4096\n"
    "1: mv t0, a2\nmv t1, a4\nli t2, 8\n"
    "2: sd t1, 0(t0)\naddi t0, t0, 8\naddi t1, t1, 1\n"
    "addi t2, t2, -1\nbnez t2, 2b\n"
    "add a2, a2, a5\naddi a4, a4, 16\naddi a3, a3, -1\nbnez a3, 1b\n"
    "fence rw, rw\n"
    ".global dirty_victim_hint\ndirty_victim_hint:\n"
    BP_PREFETCH_R_ASM("a2")
    "fence rw, rw\nld t0, 0(a2)\nli t1, 0xfeed9\n"
    "li a0, 0\nbeq t0, t1, 3f\nori a0, a0, 256\n3:\n"
    "mv a2, a1\nli a3, 8\nli a4, 0x5a00\nli a6, 1\n"
    ".global dirty_victim_verify\ndirty_victim_verify:\n"
    "4: mv t0, a2\nmv t1, a4\nli t2, 8\n"
    "5: ld t3, 0(t0)\nbeq t3, t1, 6f\nor a0, a0, a6\n6:\n"
    "addi t0, t0, 8\naddi t1, t1, 1\naddi t2, t2, -1\nbnez t2, 5b\n"
    "add a2, a2, a5\naddi a4, a4, 16\nslli a6, a6, 1\n"
    "addi a3, a3, -1\nbnez a3, 4b\nfence rw, rw\nret\n");
}

int main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile("csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:" : : : "t0", "memory");
#endif
  bp_print_string("DIRTY-VICTIM begin\n");
  uint64_t mask = exercise();
  bp_print_string("DIRTY-VICTIM mismatch_mask=");
  bp_hprint_uint64(mask);
  bp_print_string("\n");
  if (mask) {
    bp_print_string("[BSG-FAIL] detached prefetch dirty victim\n");
    bp_finish(1);
  }
  bp_print_string("[BSG-PASS] detached prefetch dirty victim\n");
  bp_finish(0);
}
