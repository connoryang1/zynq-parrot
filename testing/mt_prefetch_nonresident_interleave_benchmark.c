/* Compare four ten-request schedules from one executable and matched startup.
 * Every fresh boot selects one measured mode through a host-patched word. A
 * common dummy sequence warms all instruction bodies while a separate source
 * array keeps the measured data cold.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_prefetch.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 10
#error "Use NUM_THREADS=2 NUM_CONTEXTS=10"
#endif

#define WORKERS 10
#ifndef BENCH_DIAGNOSTIC
#define BENCH_DIAGNOSTIC 0
#endif
#define SIGNAL_BASE_ADDR ((volatile uint8_t *)0x00104000)
#define BEGIN_MARKER_BASE 0x10
#define END_MARKER_BASE   0x20

enum benchmark_mode {
  MODE_DEMAND = 0,
  MODE_BATCH = 1,
  MODE_WORKER_PREFETCH = 2,
  MODE_SWITCH_ONLY = 3,
  MODE_COUNT
};

struct line { uint64_t value, pad[7]; };
#define L(n) { (n) + 1, {0} }
#define DATA_SET { L(0),L(1),L(2),L(3),L(4),L(5),L(6),L(7),L(8),L(9) }

/* The dummy and measured arrays occupy corresponding offsets on distinct
 * pages. The common warmup never references measured_data. */
static const volatile struct line warm_data[WORKERS]
  __attribute__((aligned(4096), used)) = DATA_SET;
static const volatile struct line measured_data[WORKERS]
  __attribute__((aligned(4096), used)) = DATA_SET;

struct worker_result {
  uint64_t sum, done;
#if BENCH_DIAGNOSTIC
  uint64_t resume_cycle, load_cycle;
#endif
};
struct result_block {
  struct line avoid_data_sets[16];
  struct worker_result worker[WORKERS];
};
/* Keep result stores out of the ten cache sets occupied by either data page.
 * Otherwise benchmark bookkeeping can evict the lines being measured. */
static volatile struct result_block results __attribute__((aligned(4096), used));
static uint64_t stacks[WORKERS][128] __attribute__((aligned(64)));
/* The host overwrites this word after loading the unchanged NBF and before
 * unfreezing the core. Its symbol address is resolved from this exact ELF. */
volatile uint64_t benchmark_mode = UINT64_MAX;

/* Every logical context executes this shared body. Context-private registers
 * hold values that would otherwise require ten separately laid-out bodies:
 *   a0: data address       a1: result address     a2: runtime mode
 *   a3: next context ID    a4: done address       a5: park after lap two
 *
 * Mode 2 issues one hint before the first handoff. Modes 0 and 2 perform the
 * same load and result stores after resumption. Mode 3 performs the same two
 * complete handoff rings with those data operations removed.
 */
static __attribute__((naked, noinline, aligned(64))) void shared_worker
  (const volatile struct line *data_addr, volatile uint64_t *sum_addr,
   unsigned mode, unsigned next_context,
   volatile uint64_t *done_addr, unsigned park)
{
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, 2\n"
    "bne a2, t0, 1f\n"
    BP_PREFETCH_R_ASM("a0")
    "1: csrw 0x800, a3\n"
#if BENCH_DIAGNOSTIC
    "csrr t4, 0xcc0\n"
    "sd t4, 16(a1)\n"
#endif
    "li t0, 3\n"
    "beq a2, t0, 2f\n"
    ".global matched_worker_consume_load\n"
    "matched_worker_consume_load:\n"
    "ld t3, 0(a0)\n"
#if BENCH_DIAGNOSTIC
    "csrr t4, 0xcc0\n"
    "sd t4, 24(a1)\n"
#endif
    "sd t3, 0(a1)\n"
    "li t1, 1\n"
    "sd t1, 0(a4)\n"
    "2: csrw 0x800, a3\n"
    "beqz a5, 3f\n"
    "4: j 4b\n"
    "3: ret\n"
    ".option pop\n");
}

/* Use the same ten hint, load, sum-store and done-store operations as the
 * worker candidate, but issue them from one context without handoffs. */
static __attribute__((naked, noinline, aligned(64))) void batch_worker
  (const volatile struct line *data_addr, volatile struct worker_result *dst)
{
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "li t0, 10\n"
    "1:\n"
    BP_PREFETCH_R_ASM("a0")
    "addi a0, a0, 64\n"
    "addi t0, t0, -1\n"
    "bnez t0, 1b\n"
    "addi a0, a0, -640\n"
    "li t0, 10\n"
    "li t1, 1\n"
    "2:\n"
    ".global matched_batch_consume_load\n"
    "matched_batch_consume_load:\n"
    "ld t2, 0(a0)\n"
#if BENCH_DIAGNOSTIC
    "csrr t3, 0xcc0\n"
#endif
    "sd t2, 0(a1)\n"
    "sd t1, 8(a1)\n"
#if BENCH_DIAGNOSTIC
    "sd t3, 24(a1)\n"
#endif
    "addi a0, a0, 64\n"
#if BENCH_DIAGNOSTIC
    "addi a1, a1, 32\n"
#else
    "addi a1, a1, 16\n"
#endif
    "addi t0, t0, -1\n"
    "bnez t0, 2b\n"
    "ret\n"
    ".option pop\n");
}

static void clear_results(void)
{
  for (unsigned i = 0; i < WORKERS; ++i) {
    results.worker[i].sum = 0;
    results.worker[i].done = 0;
  }
}

/* Seed the same context fields and initialize the same result lines for every
 * mode. Only a2 differs: it is the experiment's selected operation. */
static void prepare(const volatile struct line *src, unsigned mode)
{
  clear_results();
  for (unsigned i = 1; i < WORKERS; ++i) {
    uint64_t gp_value;
    __asm__ volatile("mv %0, gp" : "=r"(gp_value));
    seed_reg(i, 3, gp_value);
    seed_reg(i, 2, (uint64_t)&stacks[i][128]);
    seed_reg(i, 10, (uint64_t)&src[i]);
    seed_reg(i, 11, (uint64_t)&results.worker[i].sum);
    seed_reg(i, 12, mode);
    seed_reg(i, 13, (i + 1) % WORKERS);
    seed_reg(i, 14, (uint64_t)&results.worker[i].done);
    seed_reg(i, 15, 1);
    seed_npc(i, (uint64_t)shared_worker);
    __asm__ volatile("fence rw, rw" : : : "memory");
  }
}

static void ring(const volatile struct line *src, unsigned mode)
{
  /* A normal C call applies the ABI clobber set across the nonresident round
   * trip; an inline call previously let a worker overwrite a live timestamp. */
  shared_worker(&src[0], &results.worker[0].sum, mode, 1,
                &results.worker[0].done, 0);
}

static void run_operation(unsigned mode, const volatile struct line *src)
{
  if (mode == MODE_BATCH)
    batch_worker(src, results.worker);
  else
    ring(src, mode);
}

static void check_results(unsigned mode)
{
  for (unsigned i = 0; i < WORKERS; ++i) {
    uint64_t expected_sum = mode == MODE_SWITCH_ONLY ? 0 : i + 1;
    uint64_t expected_done = mode == MODE_SWITCH_ONLY ? 0 : 1;
    if (results.worker[i].done != expected_done
        || results.worker[i].sum != expected_sum) {
      bp_print_string("[BSG-FAIL] worker "); bp_hprint_uint64(i);
      bp_print_string(" done/sum "); bp_hprint_uint64(results.worker[i].done);
      bp_print_string("/"); bp_hprint_uint64(results.worker[i].sum);
      bp_print_string(" expected "); bp_hprint_uint64(expected_done);
      bp_print_string("/"); bp_hprint_uint64(expected_sum);
      bp_print_string("\n");
      bp_finish(1);
    }
  }
}

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static void emit_marker(unsigned id)
{
  *SIGNAL_BASE_ADDR = id;
  __asm__ volatile("fence ow, ow" : : : "memory");
}

/* Dummy and measured calls share this exact instruction path. Prevent cloning
 * so the dummy passes also warm the code immediately following BEGIN. */
static __attribute__((noinline, noclone, aligned(64))) uint64_t run_window
  (unsigned mode, const volatile struct line *src,
   unsigned begin_marker, unsigned end_marker)
{
  emit_marker(begin_marker);
  uint64_t begin = read_global_cycle();
  run_operation(mode, src);
  uint64_t end = read_global_cycle();
  emit_marker(end_marker);
  return end - begin;
}

static void drain_traffic(void)
{
  /* Dummy data modes have already consumed all ten lines. The fence makes
   * their architectural reads/stores and context-state writes globally visible
   * before the measured setup or marker is allowed to proceed. */
  __asm__ volatile("fence rw, rw" : : : "memory");
}

static void warm_instruction_paths(void)
{
  /* Run every body in a fixed order so runtime mode selection cannot change
   * the instruction-cache or final front-end state at the measured boundary. */
  for (unsigned mode = 0; mode < MODE_COUNT; ++mode) {
    prepare(warm_data, mode);
    drain_traffic();
    run_window(mode, warm_data, 0x50 + mode, 0x40 + mode);
    drain_traffic();
    check_results(mode);
  }
}

static unsigned read_mode(void)
{
  unsigned mode = benchmark_mode;
  if (mode >= MODE_COUNT) {
    bp_print_string("[BSG-FAIL] runtime mode must be 0, 1, 2, or 3\n");
    bp_finish(1);
  }
  return mode;
}

static const char *mode_name(unsigned mode)
{
  static const char *const names[MODE_COUNT] = {
    "demand ring", "matched batch", "worker prefetch", "switch-only"
  };
  return names[mode];
}

int main(void)
{
  unsigned mode = read_mode();
  emit_marker(0x3f);
  warm_instruction_paths();

  /* This is the common measured-run boundary: identical initialization and
   * drain, warm instructions, and a data page untouched by the dummy runs. */
  prepare(measured_data, mode);
  drain_traffic();

  uint64_t cycles = run_window(mode, measured_data,
                               BEGIN_MARKER_BASE + mode,
                               END_MARKER_BASE + mode);

  check_results(mode);
  bp_print_string("Benchmark: matched ten-request schedules / two resident banks\n");
  bp_print_string("Mode: "); bp_print_string((char *)mode_name(mode));
  bp_print_string("; cycles: "); bp_hprint_uint64(cycles);
  bp_print_string("; checks: pass\n");
#if BENCH_DIAGNOSTIC
  bp_print_string("Resume cycles: ");
  for (unsigned i = 0; i < WORKERS; ++i) {
    if (i) bp_print_string(",");
    bp_hprint_uint64(results.worker[i].resume_cycle);
  }
  bp_print_string("\n");
  bp_print_string("Load completion cycles: ");
  for (unsigned i = 0; i < WORKERS; ++i) {
    if (i) bp_print_string(",");
    bp_hprint_uint64(results.worker[i].load_cycle);
  }
  bp_print_string("\n");
#endif
  bp_print_string("[BSG-PASS] ten logical nonresident prefetch workers\n");
  bp_finish(0);
  return 0;
}
