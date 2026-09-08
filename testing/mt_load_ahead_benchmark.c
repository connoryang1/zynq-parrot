/**
 * Compare matched demand-load and faulting load-ahead schedules, with useful
 * arithmetic in either the issuing context or a resident peer. Each measured
 * mode first-touches its own initialized cache lines; this is a controlled
 * microbenchmark, not a nonfaulting prefetch instruction or a speedup claim.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_load_ahead.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Load-ahead benchmark requires two resident banks and four logical contexts"
#endif

#define LINES 16
#define LINE_BYTES 64
#define WORK_ADDS 64
#define MODES 4
#define PEER_ROUNDS (4 * LINES) /* Two warmup and two measured resident modes. */
#define STR_(x) #x
#define STR(x) STR_(x)
#define LINE_VALUES { \
  [0 * LINE_BYTES] = 1, [1 * LINE_BYTES] = 2, \
  [2 * LINE_BYTES] = 3, [3 * LINE_BYTES] = 4, \
  [4 * LINE_BYTES] = 5, [5 * LINE_BYTES] = 6, \
  [6 * LINE_BYTES] = 7, [7 * LINE_BYTES] = 8, \
  [8 * LINE_BYTES] = 9, [9 * LINE_BYTES] = 10, \
  [10 * LINE_BYTES] = 11, [11 * LINE_BYTES] = 12, \
  [12 * LINE_BYTES] = 13, [13 * LINE_BYTES] = 14, \
  [14 * LINE_BYTES] = 15, [15 * LINE_BYTES] = 16 }

/* NBF initializes DRAM; guest code never initializes or reads these measured
 * lines before their selected mode. All four arrays contain identical values.
 * The separate warmup region warms code/peer control, not measured input data.
 * No cache flush or claim about downstream DRAM row state is implied. */
static volatile uint8_t cold_lines[MODES][LINES * LINE_BYTES]
  __attribute__((aligned(4096), used)) = {
    LINE_VALUES, LINE_VALUES, LINE_VALUES, LINE_VALUES
  };
static volatile uint8_t warm_lines[LINES * LINE_BYTES]
  __attribute__((aligned(4096), used)) = LINE_VALUES;
static uint64_t peer_stack[512];
static volatile uint64_t peer_result[4] __attribute__((aligned(64), used));

struct result {
  uint64_t cycles;
  uint64_t data_sum;
  uint64_t work_sum;
};

/* All hot-loop values use caller-saved registers. Every mode performs one
 * useful demand load per line; ahead modes additionally pay for lbu x0 before
 * the work. Controls do not include a redundant warming load. lbu x0 remains
 * an ordinary faulting load; only valid, cacheable addresses are used here.
 *
 * CSR 0xcc0 measures the entire loop including address updates and branches.
 * Initial/final fences, output stores, peer seeding and completion are untimed.
 * Only the resident modes charge for their two switches per line. */
#define LOOP_BEGIN \
  ".option push\n.option norvc\n" \
  "li t0, 0\nli t1, 0\nfence rw, rw\n" \
  "csrr t3, 0xcc0\n1:\n"
#define DEMAND_CONSUME \
  "lbu t2, 0(a0)\nadd t0, t0, t2\n"
#define DISCARDED_LOAD BP_LOAD_AHEAD_ASM("a0")
#define LOCAL_WORK \
  ".rept " STR(WORK_ADDS) "\naddi t1, t1, 1\n.endr\n"
#define PEER_WORK "csrwi 0x800, 1\n"
#define LOOP_END \
  "addi a0, a0, " STR(LINE_BYTES) "\n" \
  "addi a1, a1, -1\nbnez a1, 1b\n" \
  "csrr t4, 0xcc0\nsub t4, t4, t3\nfence rw, rw\n" \
  "sd t4, 0(a2)\nsd t0, 8(a2)\nsd t1, 16(a2)\n" \
  "ret\n.option pop\n"

void __attribute__((naked, noinline, aligned(64)))
load_serial(volatile uint8_t *data, uint64_t count, struct result *result)
{
  __asm__ volatile(LOOP_BEGIN DEMAND_CONSUME LOCAL_WORK LOOP_END);
}

void __attribute__((naked, noinline, aligned(64)))
load_same_context_ahead(volatile uint8_t *data, uint64_t count, struct result *result)
{
  __asm__ volatile(LOOP_BEGIN DISCARDED_LOAD LOCAL_WORK DEMAND_CONSUME LOOP_END);
}

void __attribute__((naked, noinline, aligned(64)))
load_resident_control(volatile uint8_t *data, uint64_t count, struct result *result)
{
  __asm__ volatile(LOOP_BEGIN PEER_WORK DEMAND_CONSUME LOOP_END);
}

void __attribute__((naked, noinline, aligned(64)))
load_resident_ahead(volatile uint8_t *data, uint64_t count, struct result *result)
{
  __asm__ volatile(LOOP_BEGIN DISCARDED_LOAD PEER_WORK DEMAND_CONSUME LOOP_END);
}

/* Seeded a0/a1 hold cumulative arithmetic/count; a4 holds remaining rounds.
 * A suspended peer resumes its loop tail on the next entry. After the final
 * measured round, one extra untimed handoff finishes that tail and records
 * evidence. There is no shared-memory traffic in the timed peer work. */
void __attribute__((naked, noinline, noreturn, aligned(64))) load_ahead_peer(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n1:\n"
    ".rept " STR(WORK_ADDS) "\naddi a0, a0, 1\n.endr\n"
    "addi a1, a1, 1\ncsrwi 0x800, 0\n"
    "addi a4, a4, -1\nbnez a4, 1b\n"
    "csrr a2, 0x800\nla t0, peer_result\n"
    "sd a0, 0(t0)\nsd a1, 8(t0)\nsd a2, 16(t0)\n"
    "li t1, 1\nsd t1, 24(t0)\nfence rw, rw\n"
    "csrwi 0x800, 0\n2:\nj 2b\n.option pop\n");
}

typedef void (*schedule_fn)(volatile uint8_t *, uint64_t, struct result *);

int main(void)
{
  const schedule_fn schedules[MODES] = {
    load_serial, load_same_context_ahead, load_resident_control, load_resident_ahead
  };
  char *const names[MODES] = {
    "serial demand", "same-context load-ahead",
    "resident control", "resident load-ahead"
  };
  struct result warm[MODES], measured[MODES];
  uint64_t current;

  seed_thread(1, &peer_stack[512], (uint64_t)load_ahead_peer);
  seed_reg(1, 10, 0);
  seed_reg(1, 11, 0);
  seed_reg(1, 14, PEER_ROUNDS);

  for (unsigned mode = 0; mode < MODES; ++mode)
    schedules[mode](warm_lines, LINES, &warm[mode]);
  for (unsigned mode = 0; mode < MODES; ++mode)
    schedules[mode](cold_lines[mode], LINES, &measured[mode]);

  __asm__ volatile("csrwi 0x800, 1\ncsrr %0, 0x800"
                   : "=r"(current) : : "memory");

  uint64_t valid = (current == 0)
    && (peer_result[0] == PEER_ROUNDS * WORK_ADDS)
    && (peer_result[1] == PEER_ROUNDS)
    && (peer_result[2] == 1) && (peer_result[3] == 1);
  for (unsigned mode = 0; mode < MODES; ++mode) {
    const uint64_t expected_work = mode < 2 ? LINES * WORK_ADDS : 0;
    valid &= warm[mode].data_sum == LINES * (LINES + 1) / 2;
    valid &= measured[mode].data_sum == LINES * (LINES + 1) / 2;
    valid &= warm[mode].work_sum == expected_work;
    valid &= measured[mode].work_sum == expected_work;
    valid &= warm[mode].cycles > 0 && measured[mode].cycles > 0;
  }
  if (!valid) {
    bp_print_string("[BSG-FAIL] load-ahead benchmark validation failed\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("Benchmark: faulting load-ahead, cold first-touch inputs\n");
  bp_print_string("16 lines/mode; 1 demand lbu/line; ahead adds lbu x0; 64 useful addi/line; totals in hex\n");
  for (unsigned mode = 0; mode < MODES; ++mode) {
    bp_print_string(names[mode]);
    bp_print_string(" cycles: ");
    bp_hprint_uint64(measured[mode].cycles);
    bp_print_string("\n");
  }
  bp_print_string("[BSG-PASS] load-ahead benchmark completed\n");
  bp_finish(0);
  return 0;
}
