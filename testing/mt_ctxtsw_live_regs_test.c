/**
 * mt_ctxtsw_live_regs_test.c
 *
 * Check whether caller-saved temporaries can remain live across ctxtsw. The
 * optimized microbench keeps values in a4/a5 across multiple switches, so this
 * test targets those registers directly.
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t observed_a4;
static volatile uint64_t observed_a5;
static volatile uint64_t observed_s0;
static volatile uint64_t observed_s1;
static volatile uint64_t observed_s2;
static volatile uint64_t observed_s3;
uint64_t saved_s_regs[4];

void __attribute__((naked, noinline, noreturn)) t1_entry(void);
void __attribute__((naked, noinline)) live_reg_roundtrip(void);

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x082, %0" : : "r"(v) : "memory");
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x083, %0" : : "r"(v) : "memory");
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

void __attribute__((naked, noinline, noreturn)) t1_entry(void) {
  __asm__ volatile(
    "csrwi 0x081, 0\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline)) live_reg_roundtrip(void) {
  __asm__ volatile(
    "la t0, saved_s_regs\n"
    "sd s0, 0(t0)\n"
    "sd s1, 8(t0)\n"
    "sd s2, 16(t0)\n"
    "sd s3, 24(t0)\n"
    "li a4, 0x123456789abcdef0\n"
    "li a5, 0x0fedcba987654321\n"
    "li s0, 0x1111222233334444\n"
    "li s1, 0x5555666677778888\n"
    "li s2, 0x9999aaaabbbbcccc\n"
    "li s3, 0xddddeeeeffff0001\n"
    "csrwi 0x081, 1\n"
    "la t0, observed_a4\n"
    "sd a4, 0(t0)\n"
    "la t0, observed_a5\n"
    "sd a5, 0(t0)\n"
    "la t0, observed_s0\n"
    "sd s0, 0(t0)\n"
    "la t0, observed_s1\n"
    "sd s1, 0(t0)\n"
    "la t0, observed_s2\n"
    "sd s2, 0(t0)\n"
    "la t0, observed_s3\n"
    "sd s3, 0(t0)\n"
    "la t0, saved_s_regs\n"
    "ld s0, 0(t0)\n"
    "ld s1, 8(t0)\n"
    "ld s2, 16(t0)\n"
    "ld s3, 24(t0)\n"
    "ret\n"
  );
}

int main(void) {
  uint64_t gp_val;

  __asm__ volatile("mv %0, gp" : "=r"(gp_val));
  seed_reg(1, 3 /* x3=gp */, gp_val);
  seed_reg(1, 2 /* x2=sp */, (uint64_t)&t1_stack[STACK_WORDS]);
  seed_npc(1, (uint64_t)t1_entry);

  live_reg_roundtrip();

  restore_gp();
  if (observed_a4 != 0x123456789abcdef0ULL) {
    bp_print_string("[BSG-FAIL] a4 changed across ctxtsw: ");
    bp_hprint_uint64(observed_a4);
    bp_print_string("\n");
    bp_finish(1);
  }

  if (observed_a5 != 0x0fedcba987654321ULL) {
    bp_print_string("[BSG-FAIL] a5 changed across ctxtsw: ");
    bp_hprint_uint64(observed_a5);
    bp_print_string("\n");
    bp_finish(1);
  }

  if (observed_s0 != 0x1111222233334444ULL) {
    bp_print_string("[BSG-FAIL] s0 changed across ctxtsw: ");
    bp_hprint_uint64(observed_s0);
    bp_print_string("\n");
    bp_finish(1);
  }

  if (observed_s1 != 0x5555666677778888ULL) {
    bp_print_string("[BSG-FAIL] s1 changed across ctxtsw: ");
    bp_hprint_uint64(observed_s1);
    bp_print_string("\n");
    bp_finish(1);
  }

  if (observed_s2 != 0x9999aaaabbbbccccULL) {
    bp_print_string("[BSG-FAIL] s2 changed across ctxtsw: ");
    bp_hprint_uint64(observed_s2);
    bp_print_string("\n");
    bp_finish(1);
  }

  if (observed_s3 != 0xddddeeeeffff0001ULL) {
    bp_print_string("[BSG-FAIL] s3 changed across ctxtsw: ");
    bp_hprint_uint64(observed_s3);
    bp_print_string("\n");
    bp_finish(1);
  }

  bp_print_string("[BSG-PASS] live GPRs preserved across ctxtsw\n");
  bp_finish(0);
  return 0;
}
