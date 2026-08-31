/*
 * mt_ctxtsw_nonresident_csr_bootstrap_test.c
 *
 * A freshly seeded nonresident logical context must inherit the seeding
 * context's CSR image.  In particular, a Linux user-context handoff needs
 * SATP and U-mode state; restoring reset CSR state would instead use SATP=0.
 *
 * The probe uses MSCRATCH as an execution-safe sentinel.  The RTL transfers
 * the complete packed CSR image in one assignment, so preserving this
 * writable member proves that a freshly seeded target takes the saved-image
 * restore path rather than the reset-state path.  SATP is in that same image,
 * but assigning an arbitrary nonzero SATP in bare metal would legitimately
 * enable translation with an invalid page-table root.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256
#define TEST_MSCRATCH 0xfeedfacecafebeefULL

static uint64_t t2_stack[STACK_WORDS];
static volatile uint64_t t2_mscratch;

static inline void write_ctxt(uint64_t context_id) {
  __asm__ volatile("csrw 0x800, %0" : : "r"(context_id) : "memory");
}

static inline uint64_t read_mscratch(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, mscratch" : "=r"(value));
  return value;
}

static inline void write_mscratch(uint64_t value) {
  __asm__ volatile("csrw mscratch, %0" : : "r"(value) : "memory");
}

void __attribute__((noinline, noreturn)) t2_entry(void) {
  t2_mscratch = read_mscratch();
  write_ctxt(0);
  for (;;)
    ;
}

int main(void) {
  write_mscratch(TEST_MSCRATCH);
  if (read_mscratch() != TEST_MSCRATCH) {
    bp_print_string("[BSG-FAIL] could not establish seed CSR state\n");
    bp_finish(1);
    return 1;
  }

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);
  write_ctxt(2);

  if (t2_mscratch != TEST_MSCRATCH) {
    bp_print_string("[BSG-FAIL] nonresident bootstrap lost CSR state\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] nonresident bootstrap preserved CSR state\n");
  bp_finish(0);
  return 0;
}
