/* Ten logical workers, two resident banks.  The first lap lets every worker
 * issue one request and yield; the second lap resumes each worker to consume
 * its request.  Contexts 2..9 therefore exercise the nonresident path.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_prefetch.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 10
#error "Use NUM_THREADS=2 NUM_CONTEXTS=10"
#endif

#define WORKERS 10
#ifndef BENCH_MODE
#define BENCH_MODE 2
#endif
#if BENCH_MODE < 0 || BENCH_MODE > 3
#error "BENCH_MODE must be 0 (demand), 1 (batch), 2 (prefetch), or 3 (switch-only)"
#endif
struct line { uint64_t value, pad[7]; };
#define L(n) { (n) + 1, {0} }
static const volatile struct line data[WORKERS]
  __attribute__((aligned(4096), used)) = {
  L(0),L(1),L(2),L(3),L(4),L(5),L(6),L(7),L(8),L(9)
};
struct worker_result { uint64_t sum, done; };
struct result_block {
  struct line avoid_data_sets[16];
  struct worker_result worker[WORKERS];
};
/* Keep result stores out of the ten cache sets occupied by data[].  Otherwise
 * benchmark bookkeeping can evict the very lines whose latency is measured. */
static volatile struct result_block results __attribute__((aligned(4096), used));
static uint64_t stacks[WORKERS][128] __attribute__((aligned(64)));

/* The volatile asm and memory clobber keep the hint observable to the
 * compiler; a hardware fence would only order later demand loads and cannot
 * wait for prefetch completion. */
/* Every logical context executes this same cache line.  Context-private
 * registers provide the values that used to be embedded in ten separate
 * worker bodies:
 *   a0: data address       a1: result address     a2: issue hint
 *   a3: next context ID    a4: done address       a5: park after lap two
 *
 * A context resumes immediately after each context-switch CSR.  The first lap
 * therefore issues every hint, and the second lap consumes every line.  Only
 * context 0 returns to the caller after the final handoff completes the ring.
 */
static __attribute__((naked, noinline, aligned(64))) void shared_worker
  (const volatile struct line *data_addr, volatile uint64_t *sum_addr,
   uint64_t issue_hint, unsigned next_context,
   volatile uint64_t *done_addr, unsigned park)
{
  __asm__ volatile(
    ".option push\n"
    ".option norvc\n"
    "beqz a2, 1f\n"
    "ori zero, a0, 1\n"
    "1: csrw 0x800, a3\n"
#if BENCH_MODE != 3
    "ld t3, 0(a0)\n"
    "sd t3, 0(a1)\n"
    "li t1, 1\n"
    "sd t1, 0(a4)\n"
    "csrw 0x800, a3\n"
#else
    /* Match the candidate's two complete handoff rings without memory work. */
    "csrw 0x800, a3\n"
#endif
    "bnez a5, 2f\n"
    "ret\n"
    "2: j 2b\n"
    ".option pop\n");
}

static uint64_t ring(const volatile struct line *src, unsigned hint)
{
  for (unsigned i = 0; i < WORKERS; ++i) {
    results.worker[i].sum = 0;
    results.worker[i].done = 0;
  }
  for (unsigned i = 1; i < WORKERS; ++i) {
    uint64_t gp_value;
    __asm__ volatile("mv %0, gp" : "=r"(gp_value));
    seed_reg(i, 3, gp_value);
    seed_reg(i, 2, (uint64_t)&stacks[i][128]);
    seed_reg(i, 10, (uint64_t)&src[i]);
    seed_reg(i, 11, (uint64_t)&results.worker[i].sum);
    seed_reg(i, 12, hint);
    seed_reg(i, 13, (i + 1) % WORKERS);
    seed_reg(i, 14, (uint64_t)&results.worker[i].done);
    seed_reg(i, 15, 1);
    seed_npc(i, (uint64_t)shared_worker);
    __asm__ volatile("fence rw, rw" : : : "memory");
  }
  uint64_t begin, end;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(begin) : : "memory");
  /* Use a normal C call so the compiler applies the RISC-V ABI clobber set.
   * An inline-assembly call can leave live values such as begin in t1 even
   * though the worker uses that register after a nonresident round trip. */
  shared_worker(&src[0], &results.worker[0].sum, hint, 1,
                &results.worker[0].done, 0);
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(end) : : "memory");
  for (unsigned i = 0; i < WORKERS && BENCH_MODE != 3; ++i)
    if (results.worker[i].done != 1 || results.worker[i].sum != i + 1) {
      bp_print_string("[BSG-FAIL] worker "); bp_hprint_uint64(i);
      bp_print_string(" done/sum "); bp_hprint_uint64(results.worker[i].done);
      bp_print_string("/"); bp_hprint_uint64(results.worker[i].sum);
      bp_print_string("\n");
      bp_finish(1);
    }
  return end - begin;
}

static uint64_t batch(const volatile struct line *src)
{
  uint64_t begin, end, sum = 0;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(begin) : : "memory");
  for (unsigned i = 0; i < WORKERS; ++i) bp_prefetch_r(&src[i]);
  for (unsigned i = 0; i < WORKERS; ++i) sum += src[i].value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(end) : : "memory");
  if (sum != 55) bp_finish(1);
  return end - begin;
}

int main(void)
{
  uint64_t cycles = BENCH_MODE == 1 ? batch(data) : ring(data, BENCH_MODE == 2);
  bp_print_string("Benchmark: ten logical workers / two resident banks\n");
  bp_print_string("Mode: ");
  bp_print_string(BENCH_MODE == 0 ? "nonresident demand" : BENCH_MODE == 1 ? "batched ideal" : BENCH_MODE == 2 ? "nonresident prefetch/yield/load" : "nonresident switch-only");
  bp_print_string("; cycles: "); bp_hprint_uint64(cycles); bp_print_string("\n");
  bp_print_string("[BSG-PASS] ten logical nonresident prefetch workers\n");
  bp_finish(0);
  return 0;
}
