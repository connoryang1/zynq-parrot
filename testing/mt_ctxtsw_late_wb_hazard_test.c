/**
 * mt_ctxtsw_late_wb_hazard_test.c
 *
 * Regression for cross-thread scoreboard clearing. Thread 0 launches a cold
 * load to x15/a5 and immediately requests a switch. Thread 1 then
 * launches a scored divide to the same architectural register and immediately
 * consumes it. A late T0 writeback must not clear T1's x15 hazard, and T0 must
 * receive its own load result after switching back. PASS checks correctness;
 * use the waveform to establish whether target execution overlaps the miss.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define ROUNDS 8

static uint64_t t1_stack[STACK_WORDS];
static volatile uint64_t t1_done;
static volatile uint64_t t1_observed;

static volatile uint64_t t0_load_lines[ROUNDS * 8] __attribute__((aligned(64), used)) = {
  0x9100000000000001ULL, 0x9100000000000002ULL, 0x9100000000000003ULL, 0x9100000000000004ULL,
  0x9100000000000005ULL, 0x9100000000000006ULL, 0x9100000000000007ULL, 0x9100000000000008ULL,
  0x9200000000000001ULL, 0x9200000000000002ULL, 0x9200000000000003ULL, 0x9200000000000004ULL,
  0x9200000000000005ULL, 0x9200000000000006ULL, 0x9200000000000007ULL, 0x9200000000000008ULL,
  0x9300000000000001ULL, 0x9300000000000002ULL, 0x9300000000000003ULL, 0x9300000000000004ULL,
  0x9300000000000005ULL, 0x9300000000000006ULL, 0x9300000000000007ULL, 0x9300000000000008ULL,
  0x9400000000000001ULL, 0x9400000000000002ULL, 0x9400000000000003ULL, 0x9400000000000004ULL,
  0x9400000000000005ULL, 0x9400000000000006ULL, 0x9400000000000007ULL, 0x9400000000000008ULL,
  0x9500000000000001ULL, 0x9500000000000002ULL, 0x9500000000000003ULL, 0x9500000000000004ULL,
  0x9500000000000005ULL, 0x9500000000000006ULL, 0x9500000000000007ULL, 0x9500000000000008ULL,
  0x9600000000000001ULL, 0x9600000000000002ULL, 0x9600000000000003ULL, 0x9600000000000004ULL,
  0x9600000000000005ULL, 0x9600000000000006ULL, 0x9600000000000007ULL, 0x9600000000000008ULL,
  0x9700000000000001ULL, 0x9700000000000002ULL, 0x9700000000000003ULL, 0x9700000000000004ULL,
  0x9700000000000005ULL, 0x9700000000000006ULL, 0x9700000000000007ULL, 0x9700000000000008ULL,
  0x9800000000000001ULL, 0x9800000000000002ULL, 0x9800000000000003ULL, 0x9800000000000004ULL,
  0x9800000000000005ULL, 0x9800000000000006ULL, 0x9800000000000007ULL, 0x9800000000000008ULL
};

uint64_t __attribute__((naked, noinline)) t0_roundtrip(volatile uint64_t *line);
void __attribute__((naked, noinline, noreturn)) t1_entry(void);

uint64_t __attribute__((naked, noinline)) t0_roundtrip(volatile uint64_t *line) {
  __asm__ volatile(
    "ld    a5, 0(a0)\n"
    "csrwi 0x800, 1\n"
    "mv    a0, a5\n"
    "ret\n"
  );
}

void __attribute__((naked, noinline, noreturn)) t1_entry(void) {
  __asm__ volatile(
    "divu  a5, a0, a1\n"
    "addi  a6, a5, 5\n"
    "la    t0, t1_observed\n"
    "sd    a6, 0(t0)\n"
    "li    t1, 1\n"
    "la    t0, t1_done\n"
    "sd    t1, 0(t0)\n"
    "csrwi 0x800, 0\n"
    "1:\n"
    "j     1b\n"
  );
}

int main(void) {
  bp_print_string("=== ctxtsw late writeback hazard test ===\n");

  for (uint64_t i = 0; i < ROUNDS; i++) {
    const uint64_t dividend = 0x1234567800ULL + (i * 0x10001ULL);
    const uint64_t divisor = 17ULL;
    const uint64_t expected = (dividend / divisor) + 5ULL;

    t1_done = 0;
    t1_observed = 0;

    seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
    seed_reg(1, 10 /* x10=a0 */, dividend);
    seed_reg(1, 11 /* x11=a1 */, divisor);
    seed_reg(1, 15 /* x15=a5 */, 0x5555000000000000ULL + i);

    const uint64_t loaded = t0_roundtrip(&t0_load_lines[i * 8]);
    // Compute the expected value without warming the tested cache line.
    const uint64_t expected_load = 0x9100000000000001ULL + (i << 56);
    if (loaded != expected_load) {
      bp_print_string("[BSG-FAIL] source load result changed across switch\n");
      bp_finish(1);
    }

    if (!t1_done) {
      bp_print_string("[BSG-FAIL] thread 1 did not switch back\n");
      bp_finish(1);
    }

    if (t1_observed != expected) {
      bp_print_string("[BSG-FAIL] dependent read observed ");
      bp_hprint_uint64(t1_observed);
      bp_print_string(" expected ");
      bp_hprint_uint64(expected);
      bp_print_string("\n");
      bp_finish(1);
    }
  }

  bp_print_string("[BSG-PASS] ctxtsw late writeback hazard test completed\n");
  bp_finish(0);
  return 0;
}
