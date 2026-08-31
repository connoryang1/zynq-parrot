/**
 * mt_ctxtsw_nonresident_fp_overhead_benchmark.c
 *
 * Warm/cold nonresident context-switch benchmark that keeps a broad floating
 * point register set live across every switch. The nonresident elapsed cost
 * is measured with testbench global-cycle markers: virtual CSR restore also
 * restores mcycle for the logical context.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define ROUNDS 128
#define TOTAL_SWITCHES (2 * ROUNDS)
#define FP_ENABLE_MASK (3ULL << 13)
#define HOST_SIGNAL_BASE_ADDR ((volatile uint8_t *)(HOST_DEV_BASE_ADDR | 0x04000))

static inline void global_marker(uint8_t id) {
  *HOST_SIGNAL_BASE_ADDR = id;
  __asm__ volatile("fence" ::: "memory");
}

#define FP_LOAD_SEQ \
  "li t2, 0x1111222233334444\n" "fmv.d.x f1, t2\n" \
  "li t2, 0x2222333344445555\n" "fmv.d.x f2, t2\n" \
  "li t2, 0x3333444455556666\n" "fmv.d.x f3, t2\n" \
  "li t2, 0x4444555566667777\n" "fmv.d.x f4, t2\n" \
  "li t2, 0x5555666677778888\n" "fmv.d.x f5, t2\n" \
  "li t2, 0x6666777788889999\n" "fmv.d.x f6, t2\n" \
  "li t2, 0x777788889999aaaa\n" "fmv.d.x f7, t2\n" \
  "li t2, 0x88889999aaaabbbb\n" "fmv.d.x f8, t2\n"

#define FP_CHECK_SEQ(fail_label) \
  "li t2, 0x1111222233334444\n" "fmv.x.d t1, f1\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x2222333344445555\n" "fmv.x.d t1, f2\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x3333444455556666\n" "fmv.x.d t1, f3\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x4444555566667777\n" "fmv.x.d t1, f4\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x5555666677778888\n" "fmv.x.d t1, f5\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x6666777788889999\n" "fmv.x.d t1, f6\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x777788889999aaaa\n" "fmv.x.d t1, f7\n" "bne t1, t2, " fail_label "\n" \
  "li t2, 0x88889999aaaabbbb\n" "fmv.x.d t1, f8\n" "bne t1, t2, " fail_label "\n"

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
    "li   t0, %0\n"
    "csrs mstatus, t0\n"
    "nop\nnop\nnop\nnop\n"
    FP_LOAD_SEQ
    "1:\n"
    FP_CHECK_SEQ("9f")
    "la   t0, warm_steps\n"
    "ld   t1, 0(t0)\n"
    "addi t1, t1, 1\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x800, 0\n"
    "j    1b\n"
    "9:\n"
    "la   t0, fail_code\n"
    "li   t1, 1\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x800, 0\n"
    "j    9b\n"
    :
    : "i"(FP_ENABLE_MASK)
  );
}

void __attribute__((naked, noinline, noreturn)) t2_cold_entry(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la   gp, __global_pointer$\n"
    ".option pop\n"
    "li   t0, %0\n"
    "csrs mstatus, t0\n"
    "nop\nnop\nnop\nnop\n"
    FP_LOAD_SEQ
    "1:\n"
    FP_CHECK_SEQ("9f")
    "la   t0, cold_steps\n"
    "ld   t1, 0(t0)\n"
    "addi t1, t1, 1\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x800, 0\n"
    "j    1b\n"
    "9:\n"
    "la   t0, fail_code\n"
    "li   t1, 2\n"
    "sd   t1, 0(t0)\n"
    "csrwi 0x800, 0\n"
    "j    9b\n"
    :
    : "i"(FP_ENABLE_MASK)
  );
}

static void __attribute__((noinline, aligned(8))) t0_warm_bench(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li   t1, %0\n"
    "csrs mstatus, t1\n"
    "nop\nnop\nnop\nnop\n"
    FP_LOAD_SEQ
    "li   t0, %1\n"
    "1:\n"
    FP_CHECK_SEQ("9f")
    "beqz t0, 2f\n"
    "addi t0, t0, -1\n"
    "csrwi 0x800, 1\n"
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
    : "i"(FP_ENABLE_MASK), "i"(ROUNDS)
    : "memory", "t0", "t1", "t2", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"
  );
}

static void __attribute__((noinline, aligned(8))) t0_cold_bench(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li   t1, %0\n"
    "csrs mstatus, t1\n"
    "nop\nnop\nnop\nnop\n"
    FP_LOAD_SEQ
    "li   t0, %1\n"
    "1:\n"
    FP_CHECK_SEQ("9f")
    "beqz t0, 2f\n"
    "addi t0, t0, -1\n"
    "csrwi 0x800, 2\n"
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
    : "i"(FP_ENABLE_MASK), "i"(ROUNDS)
    : "memory", "t0", "t1", "t2", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"
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
  global_marker(0xd1);
  uint64_t warm_begin = read_cycle();
  t0_warm_bench();
  uint64_t warm_end = read_cycle();
  global_marker(0xd2);
  uint64_t warm_cycles = warm_end - warm_begin;

  if (fail_code != 0 || warm_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] warm FP stress mismatch code=");
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
  global_marker(0xe1);
  uint64_t cold_begin = read_cycle();
  t0_cold_bench();
  uint64_t cold_end = read_cycle();
  global_marker(0xe2);
  uint64_t cold_cycles = cold_end - cold_begin;

  if (fail_code != 0 || cold_steps != ROUNDS) {
    bp_print_string("[BSG-FAIL] cold FP stress mismatch code=");
    bp_hprint_uint64(fail_code);
    bp_print_string(" steps=");
    bp_hprint_uint64(cold_steps);
    bp_print_string("\n");
    bp_finish(1);
    return 1;
  }

  uint64_t warm_cycles_per_switch_x100 = (warm_cycles * 100) / TOTAL_SWITCHES;

  bp_print_string("=== Nonresident FP Stress Overhead Benchmark ===\n");
  bp_print_string("Rounds/context:                  ");
  bp_hprint_uint64(ROUNDS);
  bp_print_string("\n");
  bp_print_string("Live FP regs/thread:             0x8\n");
  bp_print_string("Total switches measured:         ");
  bp_hprint_uint64(TOTAL_SWITCHES);
  bp_print_string("\n");
  bp_print_string("Warm total cycles:               ");
  bp_hprint_uint64(warm_cycles);
  bp_print_string("\n");
  bp_print_string("Warm cycles/switch x100:         ");
  bp_hprint_uint64(warm_cycles_per_switch_x100);
  bp_print_string("\n");
  bp_print_string("Warm global interval:             marker 0xd1 -> 0xd2\n");
  bp_print_string("Cold virtual rdcycle delta:      ");
  bp_hprint_uint64(cold_cycles);
  bp_print_string("\n");
  bp_print_string("Cold global interval:             marker 0xe1 -> 0xe2\n");

  bp_finish(0);
  return 0;
}
