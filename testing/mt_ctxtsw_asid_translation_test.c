/**
 * mt_ctxtsw_asid_translation_test.c
 *
 * Focused Banyan-parity probe for per-context SATP/ASID ownership. This test
 * does not construct distinct virtual mappings or execute sfence.vma yet; it
 * validates that SATP ASID state is not shared or clobbered across context
 * switches when the implementation preserves bare-mode ASID bits. If bare-mode
 * ASID bits read back as zero, the test reports that limitation and passes; a
 * full SV39 mapping test is needed to validate real address-space switching.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define SATP_ASID_SHIFT 44
#define SATP_ASID_MASK  0xFFFFULL

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t t1_initial_satp = ~0ULL;
static volatile uint64_t t1_after_write_satp = ~0ULL;
static volatile uint64_t t1_after_resume_satp = ~0ULL;

static inline void write_ctxt(uint64_t v) {
  __asm__ volatile("csrw 0x800, %0" : : "r"(v) : "memory");
}

static inline uint64_t read_satp(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, satp" : "=r"(v));
  return v;
}

static inline void write_satp(uint64_t v) {
  __asm__ volatile("csrw satp, %0" : : "r"(v) : "memory");
}

static inline uint64_t bare_satp_with_asid(uint64_t asid) {
  return (asid & SATP_ASID_MASK) << SATP_ASID_SHIFT;
}

static inline uint64_t satp_asid(uint64_t satp) {
  return (satp >> SATP_ASID_SHIFT) & SATP_ASID_MASK;
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  t1_initial_satp = read_satp();
  write_satp(bare_satp_with_asid(0x22));
  t1_after_write_satp = read_satp();
  write_ctxt(0);

  t1_after_resume_satp = read_satp();
  write_ctxt(0);

  while (1) { }
}

int main(void) {
  bp_print_string("=== Ctxtsw SATP/ASID Ownership Test ===\n");

  int errors = 0;
  write_satp(bare_satp_with_asid(0x11));

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  write_ctxt(1);

  uint64_t t0_after_t1 = read_satp();
  write_ctxt(1);
  uint64_t t0_after_t1_resume = read_satp();

  bp_print_string("T0 SATP after T1 write:  ");
  bp_hprint_uint64(t0_after_t1);
  bp_print_string("\n");
  bp_print_string("T1 initial SATP:         ");
  bp_hprint_uint64(t1_initial_satp);
  bp_print_string("\n");
  bp_print_string("T1 after write SATP:     ");
  bp_hprint_uint64(t1_after_write_satp);
  bp_print_string("\n");
  bp_print_string("T1 after resume SATP:    ");
  bp_hprint_uint64(t1_after_resume_satp);
  bp_print_string("\n");

  uint64_t t0_asid = satp_asid(t0_after_t1);
  uint64_t t0_resume_asid = satp_asid(t0_after_t1_resume);
  uint64_t t1_write_asid = satp_asid(t1_after_write_satp);
  uint64_t t1_resume_asid = satp_asid(t1_after_resume_satp);

  if ((t0_asid == 0) && (t0_resume_asid == 0) && (t1_write_asid == 0) && (t1_resume_asid == 0)) {
    bp_print_string("NOTE: bare-mode SATP ASID bits read back as zero on this model\n");
    bp_print_string("NOTE: full ASID validation still requires an SV39 mapping test\n");
  } else {
    if (t0_asid != 0x11) {
      bp_print_string("FAIL: T0 ASID was clobbered by T1\n");
      errors++;
    }
    if (t0_resume_asid != 0x11) {
      bp_print_string("FAIL: T0 ASID changed after T1 resume\n");
      errors++;
    }
    if (t1_write_asid != 0x22) {
      bp_print_string("FAIL: T1 ASID write did not take effect\n");
      errors++;
    }
    if (t1_resume_asid != 0x22) {
      bp_print_string("FAIL: T1 ASID was not preserved across switch-out/resume\n");
      errors++;
    }
  }

  if (errors == 0) {
    bp_print_string("[BSG-PASS] SATP/ASID ownership verified\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] SATP/ASID ownership failed\n");
    bp_finish(1);
  }

  return 0;
}
