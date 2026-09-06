/**
 * mt_abi_preservation_test.c
 *
 * Verify that T0's ABI-relevant integer state survives a T0->T1->T0 switch.
 *
 * Rationale:
 *   The remaining console corruption looks like post-switch C code is resuming
 *   with some live register state damaged. The compiler commonly uses `gp` and
 *   `s*` callee-saved registers while walking strings and formatting output.
 *
 * Method:
 *   - T0 seeds unique sentinels into gp and s0-s11
 *   - switch to T1, which immediately switches back
 *   - T0 snapshots gp and s0-s11 before doing any complex printing
 *   - report mismatches
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn)) t1_entry(void);

static inline void write_ctxt_1(void) {
  __asm__ volatile("csrwi 0x800, 1");
}

static inline void write_ctxt_0(void) {
  __asm__ volatile("csrwi 0x800, 0");
}

static inline void restore_gp(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la gp, __global_pointer$\n"
    ".option pop\n"
    :
    :
    : "gp"
  );
}

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, cycle" : "=r"(v));
  return v;
}

static inline void snapshot_abi_regs(uint64_t out[13]) {
  __asm__ volatile(
    "mv t0, gp\n"
    "sd t0, 0(%0)\n"
    "sd s0, 8(%0)\n"
    "sd s1, 16(%0)\n"
    "sd s2, 24(%0)\n"
    "sd s3, 32(%0)\n"
    "sd s4, 40(%0)\n"
    "sd s5, 48(%0)\n"
    "sd s6, 56(%0)\n"
    "sd s7, 64(%0)\n"
    "sd s8, 72(%0)\n"
    "sd s9, 80(%0)\n"
    "sd s10, 88(%0)\n"
    "sd s11, 96(%0)\n"
    :
    : "r"(out)
    : "memory", "t0"
  );
}

static inline void seed_t0_abi_regs(uint64_t vals[13]) {
  __asm__ volatile(
    "mv gp, %0\n"
    "mv s0, %1\n"
    "mv s1, %2\n"
    "mv s2, %3\n"
    "mv s3, %4\n"
    "mv s4, %5\n"
    "mv s5, %6\n"
    "mv s6, %7\n"
    "mv s7, %8\n"
    "mv s8, %9\n"
    "mv s9, %10\n"
    "mv s10, %11\n"
    "mv s11, %12\n"
    :
    : "r"(vals[0]), "r"(vals[1]), "r"(vals[2]), "r"(vals[3]), "r"(vals[4])
      , "r"(vals[5]), "r"(vals[6]), "r"(vals[7]), "r"(vals[8]), "r"(vals[9])
      , "r"(vals[10]), "r"(vals[11]), "r"(vals[12])
    : "memory"
  );
}

void __attribute__((naked, noinline, noreturn)) t1_entry(void) {
  __asm__ volatile(
    "csrwi 0x800, 0\n"
    "1:\n"
    "j 1b\n"
  );
}

int main(void) {
  uint64_t gp_val;
  uint64_t expected[13];
  uint64_t observed[13];

  __asm__ volatile("mv %0, gp" : "=r"(gp_val));
  expected[0] = gp_val;
  for (int i = 1; i < 13; i++)
    expected[i] = 0x1111111111111111ULL * (uint64_t)i;

  seed_reg(1, 3 /* gp */, gp_val);
  seed_reg(1, 2 /* sp */, (uint64_t)&t1_stack[STACK_WORDS]);
  seed_npc(1, (uint64_t)t1_entry);

  seed_t0_abi_regs(expected);
  (void)read_cycle();
  write_ctxt_1();
  snapshot_abi_regs(observed);

  for (int i = 0; i < 13; i++) {
    if (observed[i] != expected[i])
      bp_finish(1);
  }

  restore_gp();
  bp_print_string("[BSG-PASS] ABI state preserved across ctxtsw\n");
  bp_finish(0);

  return 0;
}
