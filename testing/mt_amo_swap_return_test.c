/**
 * Verify the AMOSWAP.W value returned to the integer register file.
 *
 * OpenSBI uses this exact zero-to-one exchange to elect the boot hart.  A
 * wrong old value sends the only FPGA hart into the secondary-hart wait loop
 * before the firmware console is initialized.
 */

#include <stdint.h>
#include "bp_utils.h"

static volatile uint32_t lottery_word __attribute__((aligned(16))) = 0;

static inline uint64_t amoswap_w_branch(volatile uint32_t *address,
                                        uint32_t value,
                                        uint64_t *branch_nonzero) {
  uint64_t old_value;
  uint64_t nonzero;
  /*
   * Match OpenSBI's boot lottery exactly: a6 initially holds the nonzero
   * address and is also the AMO destination consumed by the next branch.
   * This exercises the speculative memory-result catchup path; using a
   * separate destination register can accidentally start with the expected
   * zero and hide a broken correction.
   */
  __asm__ volatile("mv a6, %2\n\t"
                   "mv a7, %3\n\t"
                   "amoswap.w a6, a7, (a6)\n\t"
                   "beqz a6, 1f\n\t"
                   "li %1, 1\n\t"
                   "j 2f\n"
                   "1:\n\t"
                   "li %1, 0\n"
                   "2:\n\t"
                   "mv %0, a6"
                   : "=&r"(old_value), "=&r"(nonzero)
                   : "r"(address), "r"(value)
                   : "a6", "a7", "memory");
  *branch_nonzero = nonzero;
  return old_value;
}

int main(void) {
  uint64_t first_branch_nonzero;
  uint64_t second_branch_nonzero;
  const uint64_t first_old =
    amoswap_w_branch(&lottery_word, 1, &first_branch_nonzero);
  const uint32_t after_first = lottery_word;
  const uint64_t second_old =
    amoswap_w_branch(&lottery_word, 0, &second_branch_nonzero);
  const uint32_t after_second = lottery_word;

  bp_print_string("=== AMOSWAP.W Return Test ===\n");
  bp_print_string("first old:    ");
  bp_hprint_uint64(first_old);
  bp_print_string("\nfirst memory: ");
  bp_hprint_uint64(after_first);
  bp_print_string("\nsecond old:   ");
  bp_hprint_uint64(second_old);
  bp_print_string("\nsecond memory:");
  bp_hprint_uint64(after_second);
  bp_print_string("\nfirst branch nonzero: ");
  bp_hprint_uint64(first_branch_nonzero);
  bp_print_string("\nsecond branch nonzero:");
  bp_hprint_uint64(second_branch_nonzero);
  bp_print_string("\n");

  if ((first_old == 0) && (after_first == 1)
      && (second_old == 1) && (after_second == 0)
      && (first_branch_nonzero == 0) && (second_branch_nonzero == 1)) {
    bp_print_string("[BSG-PASS] AMOSWAP.W returned the previous memory value\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] AMOSWAP.W return or memory value mismatch\n");
    bp_finish(1);
  }

  return 0;
}
