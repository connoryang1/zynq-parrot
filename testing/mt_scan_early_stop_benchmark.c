/*
 * Scan an ordered in-memory index until three records qualify, or the requested
 * range ends. Compare explicit iterator, integer software coroutine, resident
 * hardware coroutine, and nonresident hardware coroutine with identical batches.
 * This is a scan microbenchmark, not full YCSB E, a B+ tree, or I/O overlap.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Use two resident banks and four logical contexts"
#endif

#define ROWS 512
#define QUERIES 8
#define MAX_BATCH 100
struct row { uint64_t key, value; };
static struct row rows[ROWS];
static struct { unsigned start, limit; } queries[QUERIES];
static volatile struct {
  unsigned fresh, start, end, batch, count;
  uint64_t values[MAX_BATCH];
} box;
static unsigned mode;
static uint64_t stack[512] __attribute__((aligned(16)));

/* Cooperative integer ABI: ra, sp, s0-s11 only. Both backends share gp/tp;
 * no floating-point code or OS scheduler is involved. The outgoing call's
 * caller-saved registers are already handled by the compiler in BOTH modes.
 */
struct context { uint64_t ra, sp, s[12]; };
static struct context caller, worker;
static void __attribute__((naked, noinline))
swap(struct context *from, struct context *to)
{
  __asm__ volatile (
    "sd ra, 0(a0)\nsd sp, 8(a0)\n"
    "sd s0, 16(a0)\nsd s1, 24(a0)\nsd s2, 32(a0)\nsd s3, 40(a0)\n"
    "sd s4, 48(a0)\nsd s5, 56(a0)\nsd s6, 64(a0)\nsd s7, 72(a0)\n"
    "sd s8, 80(a0)\nsd s9, 88(a0)\nsd s10, 96(a0)\nsd s11, 104(a0)\n"
    "ld ra, 0(a1)\nld sp, 8(a1)\n"
    "ld s0, 16(a1)\nld s1, 24(a1)\nld s2, 32(a1)\nld s3, 40(a1)\n"
    "ld s4, 48(a1)\nld s5, 56(a1)\nld s6, 64(a1)\nld s7, 72(a1)\n"
    "ld s8, 80(a1)\nld s9, 88(a1)\nld s10, 96(a1)\nld s11, 104(a1)\nret\n"
    ::: "memory");
}

static void __attribute__((noinline)) hardware_swap(uint64_t target)
{
  /* Use the accepted immediate-target interface. A register-target form fed
   * by a recent ALU result exposed stale target selection in the first run;
   * this benchmark does not fix or validate that separate RTL path. */
  if (target == 0) __asm__ volatile ("csrwi 0x800, 0" ::: "memory");
  else if (target == 1) __asm__ volatile ("csrwi 0x800, 1" ::: "memory");
  else __asm__ volatile ("csrwi 0x800, 2" ::: "memory");
}

static void handoff(unsigned produce)
{
  if (mode == 1) swap(produce ? &caller : &worker, produce ? &worker : &caller);
  else hardware_swap(produce ? (mode == 2 ? 1 : 2) : 0);
}

/* Shared batch production, including the same buffer writes in every mode. */
static unsigned __attribute__((noinline)) fill(unsigned *next)
{
  unsigned n = box.end - *next;
  if (n > box.batch) n = box.batch;
  for (unsigned i = 0; i < n; ++i) box.values[i] = rows[*next + i].value;
  *next += n;
  return n;
}

static void __attribute__((noreturn)) producer(void)
{
  unsigned next = 0;
  for (;;) {
    if (box.fresh) next = box.start;
    box.count = fill(&next);
    handoff(0);
  }
}

static unsigned lower_bound(uint64_t key)
{
  unsigned lo = 0, hi = ROWS;
  while (lo < hi) {
    unsigned mid = (lo + hi) / 2;
    if (rows[mid].key < key) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

static inline uint64_t cycle(void)
{
  uint64_t value;
  __asm__ volatile ("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

struct result { uint64_t cycles, sum, consumed, fetched, batches; };
static struct result results[4][4][2];

static struct result run(unsigned backend, unsigned batch)
{
  mode = backend;
  worker = (struct context){ .ra = (uint64_t)producer,
                             .sp = (uint64_t)&stack[512] };
  if (mode >= 2) seed_thread(mode == 2 ? 1 : 2, &stack[512], (uint64_t)producer);
  /* Prime both coroutine paths before timing; producer remains parked. */
  box.fresh = 1; box.start = 0; box.end = 1; box.batch = batch;
  if (mode) handoff(1);

  struct result r = {0};
  uint64_t begin = cycle();
  for (unsigned q = 0; q < QUERIES; ++q) {
    unsigned next = lower_bound((uint64_t)queries[q].start * 2);
    box.start = next;
    box.end = next + queries[q].limit;
    if (box.end > ROWS) box.end = ROWS;
    box.fresh = 1;
    unsigned remaining = box.end - next, matches = 0;
    while (remaining && matches < 3) {
      if (mode) handoff(1);
      else box.count = fill(&next);
      box.fresh = 0;
      unsigned n = box.count;
      r.fetched += n; ++r.batches;
      for (unsigned i = 0; i < n && matches < 3; ++i) {
        uint64_t value = box.values[i];
        ++r.consumed;
        if ((value & 3) == 0) { r.sum += value; ++matches; }
      }
      remaining -= n;
    }
  }
  r.cycles = cycle() - begin;
  return r;
}

/* Independent unbatched oracle checks early-stop results AND batch overfetch. */
static struct result reference(unsigned batch)
{
  struct result r = {0};
  for (unsigned q = 0; q < QUERIES; ++q) {
    unsigned start = queries[q].start, n = queries[q].limit;
    if (n > ROWS - start) n = ROWS - start;
    unsigned used = 0, matches = 0;
    while (used < n && matches < 3) {
      uint64_t value = rows[start + used++].value;
      if ((value & 3) == 0) { r.sum += value; ++matches; }
    }
    unsigned batches = (used + batch - 1) / batch;
    unsigned fetched = batches * batch;
    r.consumed += used; r.fetched += fetched < n ? fetched : n;
    r.batches += batches;
  }
  return r;
}

static int equal(struct result a, struct result b)
{
  return a.sum == b.sum && a.consumed == b.consumed
      && a.fetched == b.fetched && a.batches == b.batches;
}

int main(void)
{
  uint64_t rng = 0x314159;
  for (unsigned i = 0; i < ROWS; ++i) {
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    rows[i] = (struct row){ i * 2, rng };
  }
  for (unsigned q = 0; q < QUERIES; ++q) {
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    queries[q].start = rng % ROWS;
    queries[q].limit = 1 + ((rng >> 16) % 100);
  }
  /* Include full range, early-stop, and end-of-index boundaries. */
  queries[0].start = ROWS - 1; queries[0].limit = 100;
  queries[1].start = 0; queries[1].limit = 1;
  queries[2].start = ROWS; queries[2].limit = 1;
  const unsigned batches[4] = {1, 4, 16, 100};
  for (unsigned b = 0; b < 4; ++b) {
    bp_print_string("[BSG-INFO] scan batch ");
    bp_hprint_uint64(batches[b]); bp_print_string("\n");
    struct result expected = reference(batches[b]);
    for (unsigned m = 0; m < 4; ++m)
      if (!equal(run(m, batches[b]), expected)) goto fail;
    for (unsigned repeat = 0; repeat < 2; ++repeat)
      for (unsigned j = 0; j < 4; ++j) {
        unsigned m = repeat ? 3 - j : j;
        results[b][m][repeat] = run(m, batches[b]);
        if (!equal(results[b][m][repeat], expected)) goto fail;
      }
  }
  bp_print_string("=== Scan Early-stop Benchmark ===\n");
  bp_print_string("mode: 0=iterator 1=software 2=resident 3=nonresident\n");
  bp_print_string("hex columns: batch mode cycles0 cycles1 consumed fetched batches\n");
  for (unsigned b = 0; b < 4; ++b)
    for (unsigned m = 0; m < 4; ++m) {
        struct result r = results[b][m][0];
        uint64_t fields[] = {batches[b], m, r.cycles, results[b][m][1].cycles,
                             r.consumed, r.fetched, r.batches};
        bp_print_string("[SCAN] ");
        for (unsigned f = 0; f < 7; ++f) { bp_hprint_uint64(fields[f]); bp_print_string(" "); }
        bp_print_string("\n");
      }
  bp_print_string("[BSG-PASS] all scan results and overfetch counts match\n");
  bp_finish(0);
  return 0;
fail:
  bp_print_string("[BSG-FAIL] scan oracle mismatch\n");
  bp_finish(1);
  return 1;
}
