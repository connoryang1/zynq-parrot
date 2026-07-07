/**
 * mt_ctxtsw_gpr_ring_stress.c
 *
 * GPR preservation through a full T0->T1->T2->T3->T0 ring.
 *
 * T0 loads distinctive magic constants into a4, a5, and s0-s3 using naked
 * asm, then drives the ring. T1/T2/T3 are minimal stubs that immediately pass
 * control to the next context. T0 verifies all six registers hold their
 * original values when it resumes.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

/* Written by the ring-roundtrip asm stub after the ring completes */
static volatile uint64_t observed_a4;
static volatile uint64_t observed_a5;
static volatile uint64_t observed_s0;
static volatile uint64_t observed_s1;
static volatile uint64_t observed_s2;
static volatile uint64_t observed_s3;

/* Spill area for T0's callee-saved registers */
uint64_t saved_s_regs[4];

void __attribute__((naked, noinline, noreturn)) t1_stub(void) {
  __asm__ volatile(
    "csrwi 0x081, 2\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t2_stub(void) {
  __asm__ volatile(
    "csrwi 0x081, 3\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t3_stub(void) {
  __asm__ volatile(
    "csrwi 0x081, 0\n"
    "1:\n"
    "j 1b\n"
  );
}

void __attribute__((naked, noinline)) gpr_ring_roundtrip(void) {
  __asm__ volatile(
    /* Spill callee-saved regs that we're about to clobber */
    "la   t0, saved_s_regs\n"
    "sd   s0,  0(t0)\n"
    "sd   s1,  8(t0)\n"
    "sd   s2, 16(t0)\n"
    "sd   s3, 24(t0)\n"

    /* Load magic patterns into the six registers under test */
    "li   a4, 0x123456789abcdef0\n"
    "li   a5, 0x0fedcba987654321\n"
    "li   s0, 0x1111222233334444\n"
    "li   s1, 0x5555666677778888\n"
    "li   s2, 0x9999aaaabbbbcccc\n"
    "li   s3, 0xddddeeeeffff0001\n"

    /* Drive the ring: T0 -> T1 -> T2 -> T3 -> T0 */
    "csrwi 0x081, 1\n"

    /* T0 resumes here; store observed values to memory */
    "la   t0, observed_a4\n"  "sd   a4, 0(t0)\n"
    "la   t0, observed_a5\n"  "sd   a5, 0(t0)\n"
    "la   t0, observed_s0\n"  "sd   s0, 0(t0)\n"
    "la   t0, observed_s1\n"  "sd   s1, 0(t0)\n"
    "la   t0, observed_s2\n"  "sd   s2, 0(t0)\n"
    "la   t0, observed_s3\n"  "sd   s3, 0(t0)\n"

    /* Restore callee-saved regs */
    "la   t0, saved_s_regs\n"
    "ld   s0,  0(t0)\n"
    "ld   s1,  8(t0)\n"
    "ld   s2, 16(t0)\n"
    "ld   s3, 24(t0)\n"

    "ret\n"
  );
}

static inline void restore_gp(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la gp, __global_pointer$\n"
    ".option pop\n"
    : : : "gp"
  );
}

int main(void) {
  bp_print_string("=== GPR Ring Stress Test ===\n");
  bp_print_string("Ring: T0->T1->T2->T3->T0. Verifies a4, a5, s0-s3 survive the ring.\n\n");

  /* Seed all three ring threads before the roundtrip */
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_stub);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_stub);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_stub);

  gpr_ring_roundtrip();

  restore_gp();

  int errors = 0;

#define CHECK_REG(name, got, want) \
  bp_print_string(name ": "); \
  bp_hprint_uint64(got); \
  if ((got) != (want)) { \
    bp_print_string(" *** FAIL (want "); \
    bp_hprint_uint64(want); \
    bp_print_string(")"); \
    errors++; \
  } else { \
    bp_print_string(" PASS"); \
  } \
  bp_print_string("\n");

  CHECK_REG("a4", observed_a4, 0x123456789abcdef0ULL);
  CHECK_REG("a5", observed_a5, 0x0fedcba987654321ULL);
  CHECK_REG("s0", observed_s0, 0x1111222233334444ULL);
  CHECK_REG("s1", observed_s1, 0x5555666677778888ULL);
  CHECK_REG("s2", observed_s2, 0x9999aaaabbbbccccULL);
  CHECK_REG("s3", observed_s3, 0xddddeeeeffff0001ULL);

  bp_print_string("\n");
  if (errors == 0) {
    bp_print_string("[BSG-PASS] all GPRs preserved through 4-context ring\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] GPR corruption detected in 4-context ring\n");
    bp_finish(1);
  }
  return 0;
}
