/* Measure processor-visible first-touch load latency and prefetch lead time.
 * Initialized measured lines are never read by guest startup or warmup. These
 * intervals include the core/cache/interconnect path and timer instructions;
 * they are not isolated DDR timings. No cache invalidation is assumed.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "bp_prefetch.h"

#define SAMPLES 16
#define LEADS 6
#ifndef DDR_LATENCY_VERBOSE
#define DDR_LATENCY_VERBOSE 1
#endif
#define VALUE_BASE UINT64_C(0x123456789abc0000)
#define STR_(x) #x
#define STR(x) STR_(x)
struct line { uint64_t value, pad[7]; };
#define L(n) { VALUE_BASE + (n) + 1, {0} }
#define ROW { L(0), L(1), L(2), L(3), L(4), L(5), L(6), L(7), \
              L(8), L(9), L(10), L(11), L(12), L(13), L(14), L(15) }
static const volatile struct line cold_data[1 + LEADS][SAMPLES]
  __attribute__((aligned(4096), used)) = { ROW, ROW, ROW, ROW, ROW, ROW, ROW };
static const volatile struct line warm_data[SAMPLES]
  __attribute__((aligned(4096), used)) = ROW;

struct result {
  uint64_t first_cycles, second_cycles, first_value, second_value;
};
static struct result empty_results[SAMPLES], pair_results[SAMPLES];
static struct result lead_results[LEADS][SAMPLES];
static struct result dummy;

/* BlackParrot issues in order: the dependent ADDI blocks the following CSR
 * until the LD result is available. The ADDI's value is checked after timing.
 * Both cold and immediate-hot windows use exactly CSRR/LD/ADDI/CSRR. There is
 * no result store or other memory access between the two loads. The fence is
 * outside both windows; it does not assert a DDR row/cache flush.
 */
static __attribute__((naked, noinline, aligned(64))) void measure_pair
  (const volatile struct line *data, struct result *out)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "fence rw, rw\n"
    "csrr t0, 0xcc0\nld t1, 0(a0)\naddi t1, t1, 1\ncsrr t2, 0xcc0\n"
    "csrr t3, 0xcc0\nld t4, 0(a0)\naddi t4, t4, 1\ncsrr t5, 0xcc0\n"
    "sub t2, t2, t0\nsub t5, t5, t3\n"
    "sd t2, 0(a1)\nsd t5, 8(a1)\nsd t1, 16(a1)\nsd t4, 24(a1)\n"
    "ret\n.option pop\n");
}

/* Same number of instructions and dependent arithmetic as a load window,
 * replacing LD with a register copy. Report raw values; subtraction is only
 * an estimate of incremental first-touch cost, not a pure memory latency.
 */
static __attribute__((naked, noinline, aligned(64))) void measure_empty
  (uint64_t value, struct result *out)
{
  __asm__ volatile(
    ".option push\n.option norvc\nfence rw, rw\n"
    "csrr t0, 0xcc0\naddi t1, a0, 0\naddi t1, t1, 1\ncsrr t2, 0xcc0\n"
    "csrr t3, 0xcc0\naddi t4, a0, 0\naddi t4, t4, 1\ncsrr t5, 0xcc0\n"
    "sub t2, t2, t0\nsub t5, t5, t3\n"
    "sd t2, 0(a1)\nsd t5, 8(a1)\nsd t1, 16(a1)\nsd t4, 24(a1)\n"
    "ret\n.option pop\n");
}

/* first_cycles is the remaining consuming-load interval. second_cycles is
 * BEFORE-hint CSR to load-start CSR, including the hint, nominal N dependent
 * adds and timer overhead. It is an instrumented lead interval, not the exact
 * AXI-request-to-load-dispatch distance. Every condition uses untouched lines.
 * second_value checks all nominal lead instructions actually executed.
 */
#define DEFINE_LEAD(N) \
static __attribute__((naked, noinline, aligned(64))) void measure_lead_##N \
  (const volatile struct line *data, struct result *out) \
{ \
  __asm__ volatile( \
    ".option push\n.option norvc\nli t5, 0\nfence rw, rw\n" \
    "csrr t4, 0xcc0\n" BP_PREFETCH_R_ASM("a0") \
    ".rept " STR(N) "\naddi t5, t5, 1\n.endr\n" \
    "csrr t0, 0xcc0\nld t1, 0(a0)\naddi t1, t1, 1\ncsrr t2, 0xcc0\n" \
    "sub t2, t2, t0\nsub t4, t0, t4\n" \
    "sd t2, 0(a1)\nsd t4, 8(a1)\nsd t1, 16(a1)\nsd t5, 24(a1)\n" \
    "ret\n.option pop\n"); \
}
DEFINE_LEAD(0)
DEFINE_LEAD(4)
DEFINE_LEAD(8)
DEFINE_LEAD(16)
DEFINE_LEAD(32)
DEFINE_LEAD(64)

typedef void (*measure_fn)(const volatile struct line *, struct result *);
static const measure_fn lead_functions[LEADS] = {
  measure_lead_0, measure_lead_4, measure_lead_8,
  measure_lead_16, measure_lead_32, measure_lead_64
};
static const unsigned lead_adds[LEADS] = {0, 4, 8, 16, 32, 64};

static void field(char *name, uint64_t value)
{
  bp_print_string(name);
  bp_hprint_uint64(value);
}

int main(void)
{
  /* Warm the exact functions immediately before each condition. No console
   * output occurs until all measurements finish. Loader initialization of
   * cold_data is required, but guest software does not touch it beforehand.
   */
  for (unsigned i = 0; i < SAMPLES; ++i)
    measure_empty(VALUE_BASE + i + 1, &dummy);
  for (unsigned i = 0; i < SAMPLES; ++i)
    measure_empty(VALUE_BASE + i + 1, &empty_results[i]);
  for (unsigned i = 0; i < SAMPLES; ++i)
    measure_pair(&warm_data[i], &dummy);
  for (unsigned i = 0; i < SAMPLES; ++i)
    measure_pair(&cold_data[0][i], &pair_results[i]);
  for (unsigned mode = 0; mode < LEADS; ++mode) {
    for (unsigned i = 0; i < SAMPLES; ++i)
      lead_functions[mode](&warm_data[i], &dummy);
    for (unsigned i = 0; i < SAMPLES; ++i)
      lead_functions[mode](&cold_data[mode + 1][i], &lead_results[mode][i]);
  }

  unsigned failures = 0;
  for (unsigned i = 0; i < SAMPLES; ++i) {
    uint64_t expected = VALUE_BASE + i + 2;
    failures += empty_results[i].first_value != expected;
    failures += empty_results[i].second_value != expected;
    failures += pair_results[i].first_value != expected;
    failures += pair_results[i].second_value != expected;
    for (unsigned mode = 0; mode < LEADS; ++mode) {
      failures += lead_results[mode][i].first_value != expected;
      failures += lead_results[mode][i].second_value != lead_adds[mode];
    }
  }
  bp_print_string("Benchmark: DDR processor-visible latency; physical cycles; hex fields\n");
#if DDR_LATENCY_VERBOSE
  for (unsigned i = 0; i < SAMPLES; ++i) {
    field("DDR_PAIR sample=", i);
    field(" address=", (uint64_t)&cold_data[0][i]);
    field(" empty1=", empty_results[i].first_cycles);
    field(" empty2=", empty_results[i].second_cycles);
    field(" cold=", pair_results[i].first_cycles);
    field(" hot=", pair_results[i].second_cycles);
    bp_print_string("\n");
  }
  for (unsigned mode = 0; mode < LEADS; ++mode)
    for (unsigned i = 0; i < SAMPLES; ++i) {
      field("DDR_LEAD adds=", lead_adds[mode]);
      field(" sample=", i);
      field(" address=", (uint64_t)&cold_data[mode + 1][i]);
      field(" before_hint_to_load_start=", lead_results[mode][i].second_cycles);
      field(" load=", lead_results[mode][i].first_cycles);
      bp_print_string("\n");
    }
#else
  /* Functional simulation can skip slow console rows after all measurements
   * and value checks. Closed waveforms retain every physical timer window. */
  bp_print_string("DDR raw sample output disabled; inspect the closed trace\n");
#endif
  if (failures) {
    field("[BSG-FAIL] DDR latency value mismatches=", failures);
    bp_print_string("\n");
    bp_finish(1);
  }
  bp_print_string("[BSG-PASS] DDR dependent-load latency and prefetch lead sweep\n");
  bp_finish(0);
  return 0;
}
