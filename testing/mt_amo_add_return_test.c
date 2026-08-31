/* Verify AMOADD.W returns the old value and commits the arithmetic update. */

#include <stdint.h>
#include "bp_utils.h"

static volatile uint32_t amo_word;

static inline uint32_t amoadd_w(volatile uint32_t *address, uint32_t value)
{
  uint32_t old;
  __asm__ volatile("amoadd.w %0, %2, (%1)"
                   : "=r"(old)
                   : "r"(address), "r"(value)
                   : "memory");
  return old;
}

int main(void)
{
  uint32_t first_old;
  uint32_t second_old;

  amo_word = 0;
  first_old = amoadd_w(&amo_word, 1);
  second_old = amoadd_w(&amo_word, 1);

  bp_print_string("=== AMOADD.W Return Test ===\n");
  bp_print_string("first old:    ");
  bp_hprint_uint64(first_old);
  bp_print_string("\nsecond old:   ");
  bp_hprint_uint64(second_old);
  bp_print_string("\nfinal memory: ");
  bp_hprint_uint64(amo_word);
  bp_print_string("\n");

  if ((first_old == 0) && (second_old == 1) && (amo_word == 2)) {
    bp_print_string("[BSG-PASS] AMOADD.W returned and updated correctly\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] AMOADD.W result mismatch\n");
    bp_finish(1);
  }

  return 0;
}
