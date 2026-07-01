/**
 * mt_ctxtsw_nonresident_fp_ring_test.c
 *
 * Repeated nonresident FP restore test for the V1A context cache path with FP
 * backing enabled. Build/run with NUM_THREADS=2 NUM_CONTEXTS=4. Logical
 * contexts 2 and 3 are both nonresident at reset, so the sequence
 * 0->2->3->2...->3->0 forces repeated evict/restore cycles through one
 * physical victim slot.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256
#define ROUNDS 4

#define T0_SENTINEL 0x1111222233334444ULL
#define T2_SENTINEL 0x2222333344445555ULL
#define T3_SENTINEL 0x3333444455556666ULL

static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

static volatile uint64_t t2_steps;
static volatile uint64_t t3_steps;
static volatile uint64_t fail_code;

static inline void enable_fp(void) {
  __asm__ volatile("csrs mstatus, %0" : : "r"(3ULL << 13) : "memory");
  __asm__ volatile("nop; nop; nop; nop" ::: "memory");
}

static inline void write_f1(uint64_t val) {
  __asm__ volatile("fmv.d.x f1, %0" : : "r"(val) : "f1");
}

static inline uint64_t read_f1(void) {
  uint64_t value;
  __asm__ volatile("fmv.x.d %0, f1" : "=r"(value));
  return value;
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
    "1:\n"
    "li    t0, %1\n"
    "fmv.x.d t1, f1\n"
    "bne   t1, t0, 9f\n"
    "la    t0, t2_steps\n"
    "ld    t1, 0(t0)\n"
    "addi  t1, t1, 1\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "csrwi 0x081, 3\n"
    "j     1b\n"
    "9:\n"
    "la    t0, fail_code\n"
    "li    t1, 2\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "csrwi 0x081, 0\n"
    "j     9b\n"
    :
    : "i"(3ULL << 13), "i"(T2_SENTINEL)
    : "memory"
  );
}

void __attribute__((naked, noinline, noreturn)) t3_entry(void) {
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
    "1:\n"
    "li    t0, %1\n"
    "fmv.x.d t1, f1\n"
    "bne   t1, t0, 9f\n"
    "la    t0, t3_steps\n"
    "ld    t1, 0(t0)\n"
    "addi  t1, t1, 1\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "li    t2, %2\n"
    "bltu  t1, t2, 2f\n"
    "csrwi 0x081, 0\n"
    "j     1b\n"
    "2:\n"
    "csrwi 0x081, 2\n"
    "j     1b\n"
    "9:\n"
    "la    t0, fail_code\n"
    "li    t1, 3\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "csrwi 0x081, 0\n"
    "j     9b\n"
    :
    : "i"(3ULL << 13), "i"(T3_SENTINEL), "i"(ROUNDS)
    : "memory"
  );
}

int main(void) {
  t2_steps = 0;
  t3_steps = 0;
  fail_code = 0;

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_entry);

  enable_fp();
  write_f1(T0_SENTINEL);
  __asm__ volatile("csrwi 0x081, 2" ::: "memory");

  if (read_f1() != T0_SENTINEL) {
    bp_print_string("[BSG-FAIL] logical context 0 lost f1 across restore\n");
    bp_finish(1);
    return 1;
  }

  if (fail_code != 0) {
    bp_print_string("[BSG-FAIL] nonresident FP thread sentinel mismatch code=");
    bp_hprint_uint64(fail_code);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  if (t2_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] logical context 2 FP steps=");
    bp_hprint_uint64(t2_steps);
    bp_print_string(" expected=");
    bp_hprint_uint64(ROUNDS);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  if (t3_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] logical context 3 FP steps=");
    bp_hprint_uint64(t3_steps);
    bp_print_string(" expected=");
    bp_hprint_uint64(ROUNDS);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] repeated nonresident FP restore ring verified\n");
  bp_finish(0);
  return 0;
}
