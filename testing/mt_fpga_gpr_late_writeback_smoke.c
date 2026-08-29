/**
 * Exercise integer register reads that coincide with a late writeback.
 *
 * FPGA block RAMs can return the old word for a read/write collision even
 * though the behavioral memory used by simulation appears write-first.  The
 * two sequences below keep the producer and consumer adjacent, matching the
 * dependency shape used by OpenSBI during coldboot selection.
 */

#include <stdint.h>

#include "bp_utils.h"

static volatile uint64_t one __attribute__((aligned(16))) = 1;

static inline uint64_t direct_load_branch(volatile uint64_t *address) {
  uint64_t nonzero;
  __asm__ volatile(
    "ld a0, 0(%1)\n\t"
    "beqz a0, 1f\n\t"
    "li %0, 1\n\t"
    "j 2f\n"
    "1:\n\t"
    "li %0, 0\n"
    "2:"
    : "=&r"(nonzero)
    : "r"(address)
    : "a0", "memory");
  return nonzero;
}

static inline uint64_t indirect_return_branch(volatile uint64_t *address) {
  uint64_t nonzero;
  __asm__ volatile(
    "mv a1, %1\n\t"
    "la t0, 3f\n\t"
    "jalr ra, t0, 0\n\t"
    "beqz a0, 1f\n\t"
    "li %0, 1\n\t"
    "j 2f\n"
    "1:\n\t"
    "li %0, 0\n\t"
    "j 2f\n"
    "3:\n\t"
    "ld a0, 0(a1)\n\t"
    "ret\n"
    "2:"
    : "=&r"(nonzero)
    : "r"(address)
    : "a0", "a1", "t0", "ra", "memory");
  return nonzero;
}

int main(void) {
  const uint64_t direct = direct_load_branch(&one);
  const uint64_t indirect = indirect_return_branch(&one);

  bp_print_string("=== FPGA GPR Late Writeback Smoke ===\n");
  bp_print_string("direct load branch:   ");
  bp_hprint_uint64(direct);
  bp_print_string("\nindirect load return: ");
  bp_hprint_uint64(indirect);
  bp_print_string("\n");

  if ((direct == 1) && (indirect == 1)) {
    bp_print_string("[BSG-PASS] late GPR writebacks reached dependent consumers\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] dependent consumer observed stale GPR data\n");
    bp_finish(1);
  }
  return 0;
}
