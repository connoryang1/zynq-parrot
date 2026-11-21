/* Protocol fixture for direct advisory I/D full64B retention, demand-copy off.
 * Ten 4096-byte-spaced lines evict target zero from each unchanged 8-way L1.
 * Checked execution is not proof of retained hits: acceptance also requires a
 * closed trace showing both backend hits and all eight normal-L1 fill beats.
 */
#include <stdint.h>
#include "bp_utils.h"

#define POLL_LIMIT 10000U
#define CONTROL 3U
#define BUSY_MASK UINT64_C(0x300)
#define WORD(w) (UINT64_C(0xd176a0943bf52e81) ^ (UINT64_C(0x1728394a5b6c7d8) * ((w) + 1)))
#define HOT __attribute__((section(".text.retained_advisory_hot"), noinline, noclone))

/* Explicit nonzero .data keeps CRT BSS clearing out of this sparse corpus.
 * Only its first 64B in each 4096B row is referenced by the fixture.
 */
static volatile uint64_t retained_advisory_data[10][512]
  __attribute__((aligned(4096), used)) = {
    [0] = {WORD(0), WORD(1), WORD(2), WORD(3), WORD(4), WORD(5), WORD(6), WORD(7)},
    [1] = {2}, [2] = {3}, [3] = {4}, [4] = {5}, [5] = {6},
    [6] = {7}, [7] = {8}, [8] = {9}, [9] = {10}
  };

/* Every function is exactly one complete line, with sixteen 32-bit executed
 * instructions. Zero alignment fill avoids emitting thousands of NOPs into
 * the sparse NBF. Function zero is called first, then nine same-set evictors.
 */
#define CODE_TARGET(n, base) \
  extern uint64_t retained_advisory_code##n(void); \
  __asm__(".pushsection .text.retained_advisory_targets,\"ax\",@progbits\n" \
    ".option push\n.option norvc\n.balign 4096,0\n" \
    ".global retained_advisory_code" #n "\n" \
    ".type retained_advisory_code" #n ",@function\n" \
    "retained_advisory_code" #n ":\naddi a0, zero, " #base "\n" \
    "addi a0, a0, 1\naddi a0, a0, 2\naddi a0, a0, 3\n" \
    "addi a0, a0, 4\naddi a0, a0, 5\naddi a0, a0, 6\n" \
    "addi a0, a0, 7\naddi a0, a0, 8\naddi a0, a0, 9\n" \
    "addi a0, a0, 10\naddi a0, a0, 11\naddi a0, a0, 12\n" \
    "addi a0, a0, 13\naddi a0, a0, 14\nret\n" \
    ".size retained_advisory_code" #n ", .-retained_advisory_code" #n "\n" \
    ".option pop\n.popsection\n");

CODE_TARGET(0, 101)
CODE_TARGET(1, 102)
CODE_TARGET(2, 103)
CODE_TARGET(3, 104)
CODE_TARGET(4, 105)
CODE_TARGET(5, 106)
CODE_TARGET(6, 107)
CODE_TARGET(7, 108)
CODE_TARGET(8, 109)
CODE_TARGET(9, 110)

/* All normal fixture control/poll code occupies another page beginning at
 * offset128, avoiding I-set0. The linked address/span must be checked before
 * running: the C section must fit below the next 4096B boundary.
 */
__asm__(".pushsection .text.retained_advisory_hot,\"ax\",@progbits\n"
        ".balign 4096,0\n.zero 128\n.popsection\n");

static inline uint64_t policy_status(void)
{
  uint64_t raw;
  __asm__ volatile("csrr %0, 0x5c2" : "=r"(raw) : : "memory");
  return raw;
}

static inline void policy(unsigned mask)
{
  __asm__ volatile("csrw 0x5c2, %0" : : "r"((uint64_t)mask) : "memory");
}

static HOT __attribute__((noreturn)) void fail(unsigned phase, uint64_t raw)
{
  bp_print_string("[BSG-FAIL] retained advisory full-line phase/status: ");
  bp_hprint_uint64(phase);
  bp_hprint_uint64(raw);
  bp_print_string("\n");
  bp_finish(1);
}

/* Direct7c0 ready means capacity, not completion;9c0 idle is only the preview
 * owner. After submission require sampled activity from each lane followed by
 * all three idle/ready snapshots. Missing activity fails instead of retrying
 * a best-effort command or pretending an early idle observation was success.
 * None of these snapshots proves global lower-L2/AXI/DRAM quiescence.
 */
static HOT uint64_t wait_idle(unsigned mask, unsigned require_activity, unsigned phase)
{
  uint64_t raw = 0, instruction_ready, preview_idle;
  unsigned seen = 0;
  for (unsigned n = 0; n < POLL_LIMIT; ++n) {
    raw = policy_status();
    __asm__ volatile("csrr %0, 0x7c0" : "=r"(instruction_ready) : : "memory");
    __asm__ volatile("csrr %0, 0x9c0" : "=r"(preview_idle) : : "memory");
    if (!(raw >> 63) || (raw & 15) != mask)
      fail(phase, raw);
    seen |= (unsigned)(raw & BUSY_MASK);
    if (!(preview_idle & 1))
      seen |= 0x200;
    if (!(raw & BUSY_MASK) && (instruction_ready & 1) && (preview_idle & 1)
        && (!require_activity || seen == BUSY_MASK))
      return raw;
  }
  fail(phase, raw);
}

int HOT main(void)
{
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile("csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:" : : : "t0", "memory");
#endif
  uint64_t raw = policy_status();
  if (!(raw >> 63) || (raw & 15) != 0 || ((raw >> 56) & 3) != 3
      || !((raw >> 16) & 0xffff) || !((raw >> 32) & 0xffff))
    fail(1, raw);

  /* No retained captures are enabled during warming. Both 5c2 clear commands
   * invalidate only retained stores; no fence.i is used to manufacture cold
   * ordinary-L1 state or destroy the completed advisory line before demand.
   */
  policy(0);
  (void)wait_idle(0, 0, 2);
  uint64_t sum = 0;
  for (unsigned w = 0; w < 8; ++w)
    sum += retained_advisory_data[0][w];
  for (unsigned line = 1; line < 10; ++line)
    sum += retained_advisory_data[line][0];
  uint64_t expected_sum = 54;
  for (unsigned w = 0; w < 8; ++w)
    expected_sum += WORD(w);
  if (sum != expected_sum)
    fail(3, sum);

  uint64_t (*const code[10])(void) = {
    retained_advisory_code0, retained_advisory_code1, retained_advisory_code2,
    retained_advisory_code3, retained_advisory_code4, retained_advisory_code5,
    retained_advisory_code6, retained_advisory_code7, retained_advisory_code8,
    retained_advisory_code9
  };
  for (unsigned line = 0; line < 10; ++line)
    if (code[line]() != 206 + line)
      fail(4, line);

  policy(CONTROL); /* I+D advisory lookup/capture; both demand-copy bits zero. */
  (void)wait_idle(CONTROL, 0, 5);
  __asm__ volatile(
    ".global retained_advisory_submit\nretained_advisory_submit:\n"
    "csrw 0x7c0, %0\ncsrw 0x9c0, %1\n"
    : : "r"((uintptr_t)retained_advisory_code0),
        "r"((uintptr_t)&retained_advisory_data[0][0]) : "memory");
  (void)wait_idle(CONTROL, 1, 6);
  __asm__ volatile(".global retained_advisory_demand\nretained_advisory_demand:" : : : "memory");
  if (retained_advisory_code0() != 206)
    fail(7, policy_status());
  for (unsigned n = 0; n < 8; ++n) {
    unsigned w = (n + 3) & 7; /* Exercise nonzero critical offset, then all words. */
    uint64_t actual = retained_advisory_data[0][w];
    if (actual != WORD(w))
      fail(8, actual);
  }
  (void)wait_idle(CONTROL, 0, 9);
  __asm__ volatile(".global retained_advisory_completed\nretained_advisory_completed:" : : : "memory");
  policy(0);
  (void)wait_idle(0, 0, 10);
  bp_print_string("[BSG-PASS] retained advisory full-line I/D checked all words completed\n");
  bp_finish(0);
}
