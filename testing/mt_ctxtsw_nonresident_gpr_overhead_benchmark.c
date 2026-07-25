/**
 * mt_ctxtsw_nonresident_gpr_overhead_benchmark.c
 *
 * Warm/cold nonresident context-switch benchmark that keeps a broad integer
 * register set live across every switch. This is intended to guard against
 * optimizing only for the light-state case.
 *
 * Warm path: logical contexts 0 and 1 are resident at reset, so 0 <-> 1 uses
 * the resident-hit forwarding path.
 *
 * Cold path: logical context 2 is nonresident at reset. Repeated 0 <-> 2
 * switching forces the nonresident restore path on every switch. The
 * nonresident elapsed cost is measured by explicit host markers around the
 * timed loop: virtual CSR restore also restores mcycle for the logical
 * context.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define ROUNDS 128
#define TOTAL_SWITCHES (2 * ROUNDS)
#define HOST_SIGNAL_BASE_ADDR ((volatile uint8_t *)(HOST_DEV_BASE_ADDR | 0x04000))

static inline void global_marker(uint8_t id) {
  *HOST_SIGNAL_BASE_ADDR = id;
  __asm__ volatile("fence" ::: "memory");
}

#define GPR_LOAD_SEQ \
  "li a0, 0x1111222233334444\n" \
  "li a1, 0x2222333344445555\n" \
  "li a2, 0x3333444455556666\n" \
  "li a3, 0x4444555566667777\n" \
  "li a4, 0x5555666677778888\n" \
  "li a5, 0x6666777788889999\n" \
  "li a6, 0x777788889999aaaa\n" \
  "li a7, 0x88889999aaaabbbb\n" \
  "li t2, 0x9999aaaabbbbcccc\n" \
  "li t3, 0xaaaabbbbccccdddd\n" \
  "li t4, 0xbbbbccccddddeeee\n" \
  "li t5, 0xccccddddeeeeffff\n" \
  "li t6, 0xddddeeeeffff0001\n"

#define GPR_CHECK_SEQ(fail_label) \
  "li t1, 0x1111222233334444\n" "bne a0, t1, " fail_label "\n" \
  "li t1, 0x2222333344445555\n" "bne a1, t1, " fail_label "\n" \
  "li t1, 0x3333444455556666\n" "bne a2, t1, " fail_label "\n" \
  "li t1, 0x4444555566667777\n" "bne a3, t1, " fail_label "\n" \
  "li t1, 0x5555666677778888\n" "bne a4, t1, " fail_label "\n" \
  "li t1, 0x6666777788889999\n" "bne a5, t1, " fail_label "\n" \
  "li t1, 0x777788889999aaaa\n" "bne a6, t1, " fail_label "\n" \
  "li t1, 0x88889999aaaabbbb\n" "bne a7, t1, " fail_label "\n" \
  "li t1, 0x9999aaaabbbbcccc\n" "bne t2, t1, " fail_label "\n" \
  "li t1, 0xaaaabbbbccccdddd\n" "bne t3, t1, " fail_label "\n" \
  "li t1, 0xbbbbccccddddeeee\n" "bne t4, t1, " fail_label "\n" \
  "li t1, 0xccccddddeeeeffff\n" "bne t5, t1, " fail_label "\n" \
  "li t1, 0xddddeeeeffff0001\n" "bne t6, t1, " fail_label "\n"

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];

static volatile uint64_t warm_steps;
static volatile uint64_t cold_steps;
static volatile uint64_t fail_code;

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("rdcycle %0" : "=r"(v));
  return v;
}

void __attribute__((naked, noinline, noreturn)) t1_warm_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la   gp, __global_pointer$\n"
    ".option pop\n"
    GPR_LOAD_SEQ
    "1:\n"
    GPR_CHECK_SEQ("9f")
    "la   t0, warm_steps\n"
    "ld   t1, 0(t0)\n"
    "addi t1, t1, 1\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x081, 0\n"
    "j    1b\n"
    "9:\n"
    "la   t0, fail_code\n"
    "li   t1, 1\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x081, 0\n"
    "j    9b\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t2_cold_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la   gp, __global_pointer$\n"
    ".option pop\n"
    GPR_LOAD_SEQ
    "1:\n"
    GPR_CHECK_SEQ("9f")
    "la   t0, cold_steps\n"
    "ld   t1, 0(t0)\n"
    "addi t1, t1, 1\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x081, 0\n"
    "j    1b\n"
    "9:\n"
    "la   t0, fail_code\n"
    "li   t1, 2\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x081, 0\n"
    "j    9b\n"
  );
}

static void __attribute__((noinline, aligned(8))) t0_warm_bench(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    GPR_LOAD_SEQ
    "li   t0, %0\n"
    "1:\n"
    GPR_CHECK_SEQ("9f")
    "beqz t0, 2f\n"
    "addi t0, t0, -1\n"
    "csrwi 0x081, 1\n"
    "j    1b\n"
    "2:\n"
    ".option pop\n"
    "ret\n"
    "9:\n"
    "la   t0, fail_code\n"
    "li   t1, 10\n"
    "sd   t1, 0(t0)\n"
    "ret\n"
    :
    : "i"(ROUNDS)
    : "memory", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "t0", "t1", "t2", "t3", "t4", "t5", "t6"
  );
}

static void __attribute__((noinline, aligned(8))) t0_cold_bench(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    GPR_LOAD_SEQ
    "li   t0, %0\n"
    "1:\n"
    GPR_CHECK_SEQ("9f")
    "beqz t0, 2f\n"
    "addi t0, t0, -1\n"
    "csrwi 0x081, 2\n"
    "j    1b\n"
    "2:\n"
    ".option pop\n"
    "ret\n"
    "9:\n"
    "la   t0, fail_code\n"
    "li   t1, 20\n"
    "sd   t1, 0(t0)\n"
    "ret\n"
    :
    : "i"(ROUNDS)
    : "memory", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "t0", "t1", "t2", "t3", "t4", "t5", "t6"
  );
}

int main(void) {
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_entry);
  warm_steps = 0;
  fail_code = 0;
  t0_warm_bench();

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_warm_entry);
  warm_steps = 0;
  fail_code = 0;
  uint64_t warm_begin = read_cycle();
  t0_warm_bench();
  uint64_t warm_end = read_cycle();
  uint64_t warm_cycles = warm_end - warm_begin;

  if (fail_code != 0 || warm_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] warm GPR stress mismatch code=");
    bp_hprint_uint64(fail_code);
    bp_print_string(" steps=");
    bp_hprint_uint64(warm_steps);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_entry);
  cold_steps = 0;
  fail_code = 0;
  t0_cold_bench();

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_cold_entry);
  cold_steps = 0;
  fail_code = 0;
  global_marker(0xc1);
  uint64_t cold_begin = read_cycle();
  t0_cold_bench();
  uint64_t cold_end = read_cycle();
  global_marker(0xc2);
  uint64_t cold_cycles = cold_end - cold_begin;

  if (fail_code != 0 || cold_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] cold GPR stress mismatch code=");
    bp_hprint_uint64(fail_code);
    bp_print_string(" steps=");
    bp_hprint_uint64(cold_steps);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  uint64_t warm_cycles_per_switch_x100 = (warm_cycles * 100) / TOTAL_SWITCHES;

  bp_print_string("=== Nonresident GPR Stress Overhead Benchmark ===\n");
  bp_print_string("Rounds/context:                  ");
  bp_hprint_uint64(ROUNDS);
  bp_print_string("\n");
  bp_print_string("Live integer regs/thread:        0xd\n");
  bp_print_string("Total switches measured:         ");
  bp_hprint_uint64(TOTAL_SWITCHES);
  bp_print_string("\n");
  bp_print_string("Warm total cycles:               ");
  bp_hprint_uint64(warm_cycles);
  bp_print_string("\n");
  bp_print_string("Warm cycles/switch x100:         ");
  bp_hprint_uint64(warm_cycles_per_switch_x100);
  bp_print_string("\n");
  bp_print_string("Cold virtual rdcycle delta:      ");
  bp_hprint_uint64(cold_cycles);
  bp_print_string("\n");
  bp_print_string("Cold global interval:             marker 0xc1 -> 0xc2\n");

  bp_finish(0);
  return 0;
}
