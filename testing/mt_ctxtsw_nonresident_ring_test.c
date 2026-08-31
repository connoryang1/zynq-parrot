/**
 * mt_ctxtsw_nonresident_ring_test.c
 *
 * Repeated nonresident restore test for the V1A context cache path.
 * Build/run with NUM_THREADS=2 NUM_CONTEXTS=4. Logical contexts 2 and 3 are
 * both nonresident at reset, so the sequence 0->2->3->2...->3->0 forces
 * repeated evict/restore cycles through one physical victim slot.
 *
 * This test checks only V1A state that is supposed to survive nonresident
 * eviction today: integer GPRs and NPC resume behavior. It intentionally does
 * not depend on nonresident CSR isolation.
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

static inline void write_s2(uint64_t value) {
  __asm__ volatile("mv s2, %0" : : "r"(value) : "s2");
}

static inline uint64_t read_s2(void) {
  uint64_t value;
  __asm__ volatile("mv %0, s2" : "=r"(value));
  return value;
}

void __attribute__((naked, noinline, noreturn)) t2_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la    gp, __global_pointer$\n"
    ".option pop\n"
    "li    s0, 0x2222333344445555\n"
    "1:\n"
    "li    t0, 0x2222333344445555\n"
    "bne   s0, t0, 9f\n"
    "la    t0, t2_steps\n"
    "ld    t1, 0(t0)\n"
    "addi  t1, t1, 1\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "csrwi 0x800, 3\n"
    "j     1b\n"
    "9:\n"
    "la    t0, fail_code\n"
    "li    t1, 2\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "csrwi 0x800, 0\n"
    "j     9b\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t3_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la    gp, __global_pointer$\n"
    ".option pop\n"
    "li    s0, 0x3333444455556666\n"
    "1:\n"
    "li    t0, 0x3333444455556666\n"
    "bne   s0, t0, 9f\n"
    "la    t0, t3_steps\n"
    "ld    t1, 0(t0)\n"
    "addi  t1, t1, 1\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "li    t2, 4\n"
    "bltu  t1, t2, 2f\n"
    "csrwi 0x800, 0\n"
    "j     1b\n"
    "2:\n"
    "csrwi 0x800, 2\n"
    "j     1b\n"
    "9:\n"
    "la    t0, fail_code\n"
    "li    t1, 3\n"
    "sd    t1, 0(t0)\n"
    "fence\n"
    "csrwi 0x800, 0\n"
    "j     9b\n"
  );
}

int main(void) {
  t2_steps = 0;
  t3_steps = 0;
  fail_code = 0;

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);
  seed_thread(3, &t3_stack[STACK_WORDS], (uint64_t)t3_entry);

  write_s2(T0_SENTINEL);
  __asm__ volatile("csrwi 0x800, 2" ::: "memory");

  if (read_s2() != T0_SENTINEL) {
    bp_print_string("[BSG-FAIL] logical context 0 lost s2 across restore\n");
    bp_finish(1);
    return 1;
  }

  if (fail_code != 0) {
    bp_print_string("[BSG-FAIL] nonresident thread sentinel mismatch code=");
    bp_hprint_uint64(fail_code);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  if (t2_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] logical context 2 steps=");
    bp_hprint_uint64(t2_steps);
    bp_print_string(" expected=");
    bp_hprint_uint64(ROUNDS);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  if (t3_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] logical context 3 steps=");
    bp_hprint_uint64(t3_steps);
    bp_print_string(" expected=");
    bp_hprint_uint64(ROUNDS);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] repeated nonresident restore ring verified\n");
  bp_finish(0);
  return 0;
}
