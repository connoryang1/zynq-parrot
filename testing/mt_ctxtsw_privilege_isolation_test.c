/**
 * mt_ctxtsw_privilege_isolation_test.c
 *
 * Bounded Banyan-parity probe for per-context privilege-control CSR state.
 *
 * This deliberately stays in machine mode. An earlier S-mode execution probe
 * can wedge the current bare-metal harness if lower-privilege switch/trap
 * behavior is not ready, so full S/U-mode execution is tracked as a separate
 * validation gap in BANYAN_PARITY.md.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define T0_MSCRATCH 0x12345678ULL
#define T1_MSCRATCH 0x87654321ULL
#define T0_MEPC     0x10000100ULL
#define T1_MEPC     0x10000200ULL
#define MSTATUS_MPP_MASK 0x1800ULL
#define MSTATUS_MPP_S    0x0800ULL
#define MSTATUS_MPP_M    0x1800ULL

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t t1_seen_mscratch = 0;
static volatile uint64_t t1_seen_mepc = 0;
static volatile uint64_t t1_seen_mstatus_mpp = 0;
static volatile uint64_t t1_resume_mscratch = 0;
static volatile uint64_t t1_resume_mepc = 0;

static inline void write_ctxt(uint64_t v) {
  __asm__ volatile("csrw 0x081, %0" : : "r"(v) : "memory");
}

static inline uint64_t read_mscratch(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, mscratch" : "=r"(v));
  return v;
}

static inline void write_mscratch(uint64_t v) {
  __asm__ volatile("csrw mscratch, %0" : : "r"(v) : "memory");
}

static inline uint64_t read_mepc(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, mepc" : "=r"(v));
  return v;
}

static inline void write_mepc(uint64_t v) {
  __asm__ volatile("csrw mepc, %0" : : "r"(v) : "memory");
}

static inline uint64_t read_mstatus(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, mstatus" : "=r"(v));
  return v;
}

static inline void write_mstatus_mpp(uint64_t mpp_bits) {
  uint64_t v = read_mstatus();
  v = (v & ~MSTATUS_MPP_MASK) | (mpp_bits & MSTATUS_MPP_MASK);
  __asm__ volatile("csrw mstatus, %0" : : "r"(v) : "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  t1_seen_mscratch = read_mscratch();
  t1_seen_mepc = read_mepc();
  t1_seen_mstatus_mpp = read_mstatus() & MSTATUS_MPP_MASK;

  write_mscratch(T1_MSCRATCH);
  write_mepc(T1_MEPC);
  write_mstatus_mpp(MSTATUS_MPP_S);
  write_ctxt(0);

  t1_resume_mscratch = read_mscratch();
  t1_resume_mepc = read_mepc();
  write_ctxt(0);

  while (1) { }
}

int main(void) {
  bp_print_string("=== Ctxtsw Privilege CSR Ownership Test ===\n");

  int errors = 0;
  write_mscratch(T0_MSCRATCH);
  write_mepc(T0_MEPC);
  write_mstatus_mpp(MSTATUS_MPP_M);

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  write_ctxt(1);

  uint64_t t0_mscratch_after_t1 = read_mscratch();
  uint64_t t0_mepc_after_t1 = read_mepc();
  uint64_t t0_mstatus_mpp_after_t1 = read_mstatus() & MSTATUS_MPP_MASK;

  write_ctxt(1);

  if (t1_seen_mscratch != 0) {
    bp_print_string("FAIL: T1 inherited T0 mscratch\n");
    errors++;
  }
  if (t1_seen_mepc != 0) {
    bp_print_string("FAIL: T1 inherited T0 mepc\n");
    errors++;
  }
  if (t0_mscratch_after_t1 != T0_MSCRATCH) {
    bp_print_string("FAIL: T0 mscratch changed after T1\n");
    errors++;
  }
  if (t0_mepc_after_t1 != T0_MEPC) {
    bp_print_string("FAIL: T0 mepc changed after T1\n");
    errors++;
  }
  if (t0_mstatus_mpp_after_t1 != MSTATUS_MPP_M) {
    bp_print_string("FAIL: T0 mstatus.MPP changed after T1\n");
    errors++;
  }
  if (t1_resume_mscratch != T1_MSCRATCH) {
    bp_print_string("FAIL: T1 mscratch was not preserved across resume\n");
    errors++;
  }
  if (t1_resume_mepc != T1_MEPC) {
    bp_print_string("FAIL: T1 mepc was not preserved across resume\n");
    errors++;
  }

  bp_print_string("T0 mscratch after T1: ");
  bp_hprint_uint64(t0_mscratch_after_t1);
  bp_print_string("\nT1 resume mscratch:   ");
  bp_hprint_uint64(t1_resume_mscratch);
  bp_print_string("\n");

  if (errors == 0) {
    bp_print_string("[BSG-PASS] privilege CSR ownership verified\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] privilege CSR ownership failed\n");
    bp_finish(1);
  }

  return 0;
}
