/**
 * mt_ctxtsw_nonresident_fp_target_test.c
 *
 * Minimal positive probe for nonresident FP restore plumbing. Build/run with
 * NUM_THREADS=2 NUM_CONTEXTS=4. Logical context 2 starts nonresident, writes
 * and verifies its own f1 state, then returns to logical context 0, which
 * checks its own f1 state was preserved.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256
#define T0_SENTINEL 0x1111222233334444ULL
#define T2_SENTINEL 0x2222333344445555ULL

static uint64_t t2_stack[STACK_WORDS];
static volatile uint64_t t2_seen;

static inline void enable_fp(void) {
  __asm__ volatile("csrs mstatus, %0" : : "r"(3ULL << 13) : "memory");
  __asm__ volatile("nop; nop; nop; nop" ::: "memory");
}

static inline void write_f1(uint64_t val) {
  __asm__ volatile("fmv.d.x f1, %0" : : "r"(val) : "f1");
}

static inline uint64_t read_f1(void) {
  uint64_t val;
  __asm__ volatile("fmv.x.d %0, f1" : "=r"(val));
  return val;
}

void __attribute__((naked, noinline, noreturn)) t2_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la    gp, __global_pointer$\n"
    ".option pop\n"
    "li    t0, %0\n"
    "csrs  mstatus, t0\n"
    "nop\n"
    "nop\n"
    "nop\n"
    "nop\n"
    "li    t0, %1\n"
    "fmv.d.x f1, t0\n"
    "fmv.x.d t1, f1\n"
    "bne   t1, t0, 1f\n"
    "la    t2, t2_seen\n"
    "li    t3, 1\n"
    "sd    t3, 0(t2)\n"
    "csrwi 0x800, 0\n"
    "j     .\n"
    "1:\n"
    "la    t2, t2_seen\n"
    "li    t3, 2\n"
    "sd    t3, 0(t2)\n"
    "csrwi 0x800, 0\n"
    "j     .\n"
    :
    : "i"(3ULL << 13), "i"(T2_SENTINEL)
    : "memory"
  );
}

int main(void) {
  t2_seen = 0;

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);

  enable_fp();
  write_f1(T0_SENTINEL);
  __asm__ volatile("csrwi 0x800, 2" ::: "memory");

  if (t2_seen != 1) {
    bp_print_string("[BSG-FAIL] nonresident FP context 2 did not verify f1, code=");
    bp_hprint_uint64(t2_seen);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  if (read_f1() != T0_SENTINEL) {
    bp_print_string("[BSG-FAIL] logical context 0 lost f1 across nonresident restore\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] nonresident FP context switch completed\n");
  bp_finish(0);
  return 0;
}
