/* Exercise independent older producers across real nonresident eviction.
 * Producer destinations never supply the immediate context-switch target.
 * Both target peers overwrite x15 and x28 before restoring the source image.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "This regression requires two physical banks and four logical contexts"
#endif

#define ROUNDS 4
#define LOW_SENTINEL 0x151ULL
#define HIGH_SENTINEL 0x171ULL
#define COLD_VALUE(i) (0x9102030405060700ULL + (uint64_t)(i))
#define LINE(i) [i] = { COLD_VALUE(i) }
static const volatile uint64_t cold_lines[ROUNDS * 4][8]
  __attribute__((aligned(64))) = {
  LINE(0), LINE(1), LINE(2), LINE(3), LINE(4), LINE(5), LINE(6), LINE(7),
  LINE(8), LINE(9), LINE(10), LINE(11), LINE(12), LINE(13), LINE(14), LINE(15)
};

struct peer_report {
  uint64_t context, initial_low, initial_high, overwritten_low, overwritten_high;
};
static volatile struct peer_report peer_reports[2];
static uint64_t peer_stacks[2][128] __attribute__((aligned(16)));
static volatile uint64_t source_report[3];

/* a4 points to a private report seeded before entry. The incoming values and
 * the values that replace them are both observable without touching a stack. */
#define PEER(name, next, low, high) \
static __attribute__((naked, noinline, noreturn)) void name(void) { \
  __asm__ volatile( \
    ".option push\n.option norvc\n" \
    "sd a5, 8(a4)\nsd t3, 16(a4)\n" \
    "csrr t0, 0x800\nsd t0, 0(a4)\n" \
    "li a5, " #low "\nli t3, " #high "\n" \
    "sd a5, 24(a4)\nsd t3, 32(a4)\n" \
    "csrwi 0x800, " #next "\n1: j 1b\n.option pop\n"); \
}
PEER(peer2, 3, 0x2a5, 0x2bc)
PEER(peer3, 0, 0x3a5, 0x3bc)

/* The syscall-like immediate switch is independent of a5/t3. Keep exact
 * producer/switch adjacency in assembly, and record source values before C
 * can reuse the caller-saved registers after return. */
typedef void (*kernel_fn)(const volatile uint64_t *, uint64_t, uint64_t,
                          volatile uint64_t *);
#define KERNEL(name, producer) \
static __attribute__((naked, noinline)) void name( \
    const volatile uint64_t *line __attribute__((unused)), \
    uint64_t dividend __attribute__((unused)), \
    uint64_t divisor __attribute__((unused)), \
    volatile uint64_t *report __attribute__((unused))) { \
  __asm__ volatile( \
    ".option push\n.option norvc\n" \
    "li a5, 0x151\nli t3, 0x171\n" \
    producer \
    ".global " #name "_handoff\n" #name "_handoff:\n" \
    "csrwi 0x800, 2\n" \
    "sd a5, 0(a3)\nsd t3, 8(a3)\n" \
    "csrr t0, 0x800\nsd t0, 16(a3)\nret\n.option pop\n"); \
}
KERNEL(low_load, "ld a5, 0(a0)\n")
KERNEL(high_load, "ld t3, 0(a0)\n")
KERNEL(low_divide, "divu a5, a1, a2\n")
KERNEL(high_divide, "divu t3, a1, a2\n")
KERNEL(low_load_high_divide, "ld a5, 0(a0)\ndivu t3, a1, a2\n")
KERNEL(high_load_low_divide, "ld t3, 0(a0)\ndivu a5, a1, a2\n")

static void prepare_peers(void)
{
  for (unsigned i = 0; i < 2; ++i) {
    unsigned context = i + 2;
    peer_reports[i].context = 0;
    peer_reports[i].initial_low = 0;
    peer_reports[i].initial_high = 0;
    peer_reports[i].overwritten_low = 0;
    peer_reports[i].overwritten_high = 0;
    seed_thread(context, &peer_stacks[i][128],
                (uint64_t)(i ? peer3 : peer2));
    seed_reg(context, 14, (uint64_t)&peer_reports[i]);
    seed_reg(context, 15, i ? 0x315 : 0x215);
    seed_reg(context, 28, i ? 0x31c : 0x21c);
  }
  source_report[0] = source_report[1] = source_report[2] = UINT64_MAX;
}

static int peers_match(void)
{
  return peer_reports[0].context == 2 && peer_reports[1].context == 3
      && peer_reports[0].initial_low == 0x215
      && peer_reports[0].initial_high == 0x21c
      && peer_reports[1].initial_low == 0x315
      && peer_reports[1].initial_high == 0x31c
      && peer_reports[0].overwritten_low == 0x2a5
      && peer_reports[0].overwritten_high == 0x2bc
      && peer_reports[1].overwritten_low == 0x3a5
      && peer_reports[1].overwritten_high == 0x3bc;
}

int main(void)
{
  const kernel_fn kernels[] = {low_load, high_load, low_divide, high_divide,
                              low_load_high_divide, high_load_low_divide};
  unsigned stage = 0;
  for (unsigned round = 0; round < ROUNDS; ++round) {
    const uint64_t dividend = 0xfedcba9876543210ULL + round * 113;
    const uint64_t divisor = 17 + round * 2;
    const uint64_t quotient = dividend / divisor;
    for (unsigned k = 0; k < 6; ++k) {
      unsigned line = round * 4 + (k < 2 ? k : k >= 4 ? k - 2 : 0);
      uint64_t low = LOW_SENTINEL, high = HIGH_SENTINEL;
      if (k == 0 || k == 4) low = COLD_VALUE(line);
      if (k == 1 || k == 5) high = COLD_VALUE(line);
      if (k == 2 || k == 5) low = quotient;
      if (k == 3 || k == 4) high = quotient;
      stage = round * 6 + k;
      prepare_peers();
      /* Address calculation never reads the tested line; each load case uses
       * a distinct line, and there is no fence between producer and switch. */
      kernels[k](&cold_lines[line][0], dividend, divisor, source_report);
      if (source_report[0] != low || source_report[1] != high
          || source_report[2] != 0 || !peers_match()) {
        bp_print_string("[BSG-FAIL] nonresident independent late result stage ");
        bp_hprint_uint64(stage);
        bp_print_string(" low/high/context ");
        bp_hprint_uint64(source_report[0]);
        bp_print_string("/"); bp_hprint_uint64(source_report[1]);
        bp_print_string("/"); bp_hprint_uint64(source_report[2]);
        bp_print_string(" expected low/high ");
        bp_hprint_uint64(low); bp_print_string("/"); bp_hprint_uint64(high);
        bp_print_string("\n");
        bp_finish(1);
        return 1;
      }
    }
  }
  bp_print_string("[BSG-PASS] independent cold-load/divide results survive nonresident eviction in both GPR lines\n");
  bp_finish(0);
  return 0;
}
