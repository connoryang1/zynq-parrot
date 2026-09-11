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
#if BENCH_MODE < 0 || BENCH_MODE > 2
#error "BENCH_MODE must be 0 (demand), 1 (batch), or 2 (prefetch)"
#endif
struct line { uint64_t value, pad[7]; };
#define L(n) { (n) + 1, {0} }
static const volatile struct line data[WORKERS]
  __attribute__((aligned(4096), used)) = {
  L(0),L(1),L(2),L(3),L(4),L(5),L(6),L(7),L(8),L(9)
};
static volatile uint64_t sums[WORKERS] __attribute__((aligned(64), used));
static volatile uint64_t done[WORKERS] __attribute__((aligned(64), used));
static uint64_t stacks[WORKERS][128] __attribute__((aligned(64)));

#define WORKER(NAME, ID, NEXT, FINAL) \
  static __attribute__((naked, noinline, aligned(64))) void NAME(void) { \
    __asm__ volatile( \
      "addi t2, a0, " #ID "*64\n" \
      "beqz a2, 1f\nori zero, t2, 1\n1: csrwi 0x800, " #NEXT "\n" \
      "ld t3, 0(t2)\n" \
      "la t0, sums\nsd t3, " #ID "*8(t0)\n" \
      "la t0, done\nli t1, 1\nsd t1, " #ID "*8(t0)\n" \
      "csrwi 0x800, " #NEXT "\n" FINAL ); }

WORKER(w0, 0, 1, "ret\n")
WORKER(w1, 1, 2, "1: j 1b\n")
WORKER(w2, 2, 3, "1: j 1b\n")
WORKER(w3, 3, 4, "1: j 1b\n")
WORKER(w4, 4, 5, "1: j 1b\n")
WORKER(w5, 5, 6, "1: j 1b\n")
WORKER(w6, 6, 7, "1: j 1b\n")
WORKER(w7, 7, 8, "1: j 1b\n")
WORKER(w8, 8, 9, "1: j 1b\n")
WORKER(w9, 9, 0, "1: j 1b\n")

static void (*const entries[WORKERS])(void) =
  { w0,w1,w2,w3,w4,w5,w6,w7,w8,w9 };

static uint64_t ring(const volatile struct line *src, unsigned hint)
{
  for (unsigned i = 0; i < WORKERS; ++i) { sums[i] = 0; done[i] = 0; }
  for (unsigned i = 1; i < WORKERS; ++i) {
    uint64_t gp_value;
    __asm__ volatile("mv %0, gp" : "=r"(gp_value));
    seed_reg(i, 3, gp_value);
    seed_reg(i, 2, (uint64_t)&stacks[i][128]);
    seed_reg(i, 10, (uint64_t)src);
    seed_reg(i, 11, (uint64_t)sums);
    seed_reg(i, 12, hint);
    seed_npc(i, (uint64_t)entries[i]);
    __asm__ volatile("fence rw, rw" : : : "memory");
  }
  uint64_t begin, end;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(begin) : : "memory");
  __asm__ volatile("mv a0,%0\nmv a1,%1\nmv a2,%2\ncall w0\n"
                   : : "r"(src), "r"((uint64_t)sums), "r"((uint64_t)hint)
                   : "a0", "a1", "a2", "memory");
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(end) : : "memory");
  for (unsigned i = 0; i < WORKERS; ++i)
    if (done[i] != 1 || sums[i] != i + 1) {
      bp_print_string("[BSG-FAIL] worker "); bp_hprint_uint64(i);
      bp_print_string(" done/sum "); bp_hprint_uint64(done[i]);
      bp_print_string("/"); bp_hprint_uint64(sums[i]); bp_print_string("\n");
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
  bp_print_string(BENCH_MODE == 0 ? "nonresident demand" : BENCH_MODE == 1 ? "batched ideal" : "nonresident prefetch/yield/load");
  bp_print_string("; cycles: "); bp_hprint_uint64(cycles); bp_print_string("\n");
  bp_print_string("[BSG-PASS] ten logical nonresident prefetch workers\n");
  bp_finish(0);
  return 0;
}
