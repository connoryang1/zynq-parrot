/**
 * mt_ctxtsw_4ctx_ring_isolation.c
 *
 * Full 4-context ring CSR isolation test.
 *
 * Ring: T0->T1->T2->T3->T0. Each thread reads its initial mscratch (must be
 * 0 at first entry), writes its own sentinel, and records the written-back
 * value to a shared result area before switching forward. T0 verifies that
 * its own sentinel survived the ring and that each thread's records are correct.
 *
 * Thread bodies use naked asm (the proven pattern from ring_stress) so there
 * is no C prologue confusion when entering via a seeded NPC.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512

#define SENTINEL_T0 0xAAAA0000AAAA0000ULL
#define SENTINEL_T1 0xBBBB1111BBBB1111ULL
#define SENTINEL_T2 0xCCCC2222CCCC2222ULL
#define SENTINEL_T3 0xDDDD3333DDDD3333ULL

#define UNSET 0xFFFFFFFFFFFFFFFFULL

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

volatile uint64_t t1_initial = UNSET;
volatile uint64_t t1_written = UNSET;
volatile uint64_t t2_initial = UNSET;
volatile uint64_t t2_written = UNSET;
volatile uint64_t t3_initial = UNSET;
volatile uint64_t t3_written = UNSET;

void __attribute__((naked, noinline, noreturn)) t1_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la    gp, __global_pointer$\n"
    ".option pop\n"
    /* read and record initial mscratch */
    "csrr  t0, mscratch\n"
    "la    t1, t1_initial\n"
    "sd    t0, 0(t1)\n"
    "fence\n"                        /* drain store before csrw (hw bug workaround) */
    /* write sentinel, record written-back value */
    "li    t0, 0xBBBB1111BBBB1111\n"
    "csrw  mscratch, t0\n"
    "csrr  t0, mscratch\n"
    "la    t1, t1_written\n"
    "sd    t0, 0(t1)\n"
    "fence\n"                        /* drain store before switch to non-T0 */
    /* switch to T2 */
    "csrwi 0x081, 2\n"
    "1:\n"
    "j     1b\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t2_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la    gp, __global_pointer$\n"
    ".option pop\n"
    "csrr  t0, mscratch\n"
    "la    t1, t2_initial\n"
    "sd    t0, 0(t1)\n"
    "fence\n"
    "li    t0, 0xCCCC2222CCCC2222\n"
    "csrw  mscratch, t0\n"
    "csrr  t0, mscratch\n"
    "la    t1, t2_written\n"
    "sd    t0, 0(t1)\n"
    "fence\n"
    "csrwi 0x081, 3\n"
    "1:\n"
    "j     1b\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t3_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la    gp, __global_pointer$\n"
    ".option pop\n"
    "csrr  t0, mscratch\n"
    "la    t1, t3_initial\n"
    "sd    t0, 0(t1)\n"
    "fence\n"
    "li    t0, 0xDDDD3333DDDD3333\n"
    "csrw  mscratch, t0\n"
    "csrr  t0, mscratch\n"
    "la    t1, t3_written\n"
    "sd    t0, 0(t1)\n"
    "fence\n"
    /* switch back to T0 */
    "csrwi 0x081, 0\n"
    "1:\n"
    "j     1b\n"
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

static inline uint64_t read_mscratch(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, mscratch" : "=r"(v));
  return v;
}

static inline void write_mscratch(uint64_t v) {
  __asm__ volatile("csrw mscratch, %0" : : "r"(v));
}

int main(void) {
  /* Pre-seed all ring threads before entering the ring */
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_entry);

  /*
   * Keep host MMIO output after the ring. Pre-ring bp_print_string() traffic
   * leaves uncached stores outstanding, and the thread bodies intentionally use
   * fences before switching. Printing here can make this test cover host I/O
   * ordering instead of CSR/thread isolation.
   */
  write_mscratch(SENTINEL_T0);
  __asm__ volatile("csrwi 0x081, 1" ::: "memory");
  /* T0 resumes here after T3 switches back */

  restore_gp();
  uint64_t t0_after = read_mscratch();

  int errors = 0;

#define CHECK_EQ(label, got, want) \
  bp_print_string(label ": "); \
  bp_hprint_uint64(got); \
  if ((got) != (want)) { \
    bp_print_string(" FAIL (want "); bp_hprint_uint64(want); bp_print_string(")"); \
    errors++; \
  } else { bp_print_string(" PASS"); } \
  bp_print_string("\n");

  CHECK_EQ("T0 mscratch after ring", t0_after,   SENTINEL_T0);
  CHECK_EQ("T1 initial mscratch",    t1_initial,  0ULL);
  CHECK_EQ("T1 written mscratch",    t1_written,  SENTINEL_T1);
  CHECK_EQ("T2 initial mscratch",    t2_initial,  0ULL);
  CHECK_EQ("T2 written mscratch",    t2_written,  SENTINEL_T2);
  CHECK_EQ("T3 initial mscratch",    t3_initial,  0ULL);
  CHECK_EQ("T3 written mscratch",    t3_written,  SENTINEL_T3);

  bp_print_string("\n");
  if (errors == 0) {
    bp_print_string("[BSG-PASS] 4-context ring CSR isolation verified\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] 4-context ring isolation failed\n");
    bp_finish(1);
  }
  return 0;
}
