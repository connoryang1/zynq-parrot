/*
 * Two independent request handlers, each walking a randomized pointer chain.
 * Compare sequential service, manually interleaved ordinary loads, and resident
 * load/yield/consume handlers. No prefetch instructions or unrelated compute.
 * This bare-metal microbenchmark measures direct cooperative round-robin, not
 * Linux pthread scheduling. Both chains finish inside every timed interval.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS < 2
#error "Two resident slots are required"
#endif

#define STEPS 64
#define HOT_NODES 8
#define PRESSURE_NODES 128
#define STR1(x) #x
#define STR(x) STR1(x)
#define BEGIN ".option push\n.option norvc\n"
#define END ".option pop\n"

/* Pressure: each chain touches 8 KiB in eight disjoint D-cache sets, with
 * sixteen lines/set versus eight ways. Combined span is 64 KiB, touched lines
 * total 16 KiB. This is intentional set pressure, not a uniform capacity test.
 * The two independently permuted rings never share a cache line or D$ set.
 */
/* Hot A/B select sets 1/2 modulo eight, disjoint from pressure A/B (0/4).
 * Padding preserves hot residency in BOTH mixed cases, not only one order. */
struct hot_node {
  uint8_t prefix[64]; uintptr_t a; uint8_t pad_a[56];
  uintptr_t b; uint8_t pad_b[376];
};
struct pressure_node { uintptr_t a; uint8_t pad_a[248]; uintptr_t b; uint8_t pad_b[248]; };
static struct hot_node hot[HOT_NODES] __attribute__((aligned(4096)));
static struct pressure_node pressure[PRESSURE_NODES] __attribute__((aligned(4096)));
static uint64_t worker_stack[128];
static volatile uint64_t worker_result;
struct pair { uint64_t a, b; };

/* An order-sensitive checksum forces every returned pointer to be consumed.
 * All modes perform exactly the same rotation/XOR per chain step. */
#define DIGEST_A \
  "slli t2, t1, 7\nsrli t3, t1, 57\nor t1, t2, t3\n" \
  "xor t1, t1, t0\nmv a0, t0\n"
#define DIGEST_B \
  "slli t2, t5, 7\nsrli t3, t5, 57\nor t5, t2, t3\n" \
  "xor t5, t5, t4\nmv a1, t4\n"

uint64_t __attribute__((naked, noinline, aligned(64)))
request_serial(uintptr_t root, uint64_t steps)
{
  __asm__ volatile(BEGIN "li t1, 0\n1:\nld t0, 0(a0)\n"
    DIGEST_A
    "addi a1, a1, -1\nbnez a1, 1b\nmv a0, t1\nret\n" END);
}

struct pair __attribute__((naked, noinline, aligned(64)))
requests_batched(uintptr_t root_a, uintptr_t root_b, uint64_t steps)
{
  __asm__ volatile(BEGIN "li t1, 0\nli t5, 0\n1:\n"
    "ld t0, 0(a0)\nld t4, 0(a1)\n"
    DIGEST_A DIGEST_B
    "addi a2, a2, -1\nbnez a2, 1b\n"
    "mv a0, t1\nmv a1, t5\nret\n" END);
}

uint64_t __attribute__((naked, noinline, aligned(64)))
request_switched(uintptr_t root, uint64_t steps)
{
  __asm__ volatile(BEGIN "li t1, 0\n1:\nld t0, 0(a0)\n"
    "csrwi 0x800, 1\n" DIGEST_A
    "addi a1, a1, -1\nbnez a1, 1b\n"
    /* B's last load has been issued but not yet consumed: include its final
     * digest and return handoff before ending the measurement. */
    "csrwi 0x800, 1\nmv a0, t1\nret\n" END);
}

void __attribute__((naked, noinline, noreturn, aligned(64))) request_worker(void)
{
  /* a0 is seeded to B's root. Only caller-saved registers are used, and each
   * context owns its own t0, including any late arriving load result. */
  __asm__ volatile(BEGIN "li a1, " STR(STEPS) "\nli t1, 0\n1:\n"
    "ld t0, 0(a0)\ncsrwi 0x800, 0\n" DIGEST_A
    "addi a1, a1, -1\nbnez a1, 1b\ncsrwi 0x800, 0\n"
    /* Digest is complete above, inside timing. Publish only when A resumes
     * us for untimed result collection, avoiding an extra timed shared store. */
    "la t0, worker_result\nsd t1, 0(t0)\ncsrwi 0x800, 0\n"
    "2:\nj 2b\n" END);
}

static inline uint64_t cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

static uint64_t random_step(uint64_t x)
{
  x ^= x << 13; x ^= x >> 7;
  return x ^ (x << 17);
}

static uintptr_t make_ring(uintptr_t base, unsigned stride, unsigned count,
                           uint64_t rng, uint64_t *expected)
{
  unsigned order[PRESSURE_NODES];
  for (unsigned i = 0; i < count; ++i) order[i] = i;
  for (unsigned i = count - 1; i; --i) {
    rng = random_step(rng);
    unsigned j = rng % (i + 1);
    unsigned tmp = order[i]; order[i] = order[j]; order[j] = tmp;
  }
  for (unsigned i = 0; i < count; ++i)
    *(uintptr_t *)(base + stride * order[i]) = base + stride * order[(i + 1) % count];
  /* Reference comes from construction metadata, not another timed-ring walk. */
  *expected = 0;
  for (unsigned i = 0; i < STEPS; ++i) {
    *expected = (*expected << 7) | (*expected >> 57);
    *expected ^= base + stride * order[(i + 1) % count];
  }
  return base + stride * order[0];
}

static uint64_t __attribute__((noinline))
run(unsigned mode, uintptr_t a, uintptr_t b, unsigned nodes, struct pair *result)
{
  struct pair value;
  if (mode == 2) {
    worker_result = 0;
    seed_thread(1, &worker_stack[128], (uint64_t)request_worker);
    seed_reg(1, 10, b);
  }
  /* Identical full-ring preconditioning, after all mode-specific setup.
   * Allocation/printing and worker initialization are outside timing. */
  (void)requests_batched(a, b, nodes);
  uint64_t begin = cycle();
  if (mode == 0) {
    value.a = request_serial(a, STEPS);
    value.b = request_serial(b, STEPS);
  } else if (mode == 1) {
    value = requests_batched(a, b, STEPS);
  } else {
    value.a = request_switched(a, STEPS);
  }
  uint64_t elapsed = cycle() - begin;
  if (mode == 2) {
    __asm__ volatile("csrwi 0x800, 1" ::: "memory");
    value.b = worker_result;
  }
  *result = value;
  return elapsed;
}

int main(void)
{
  struct pair expected[4], observed;
  uintptr_t roots[4][2];
  uint64_t times[4][6];
  const unsigned order[6] = {0, 1, 2, 2, 1, 0};
  roots[0][0] = make_ring((uintptr_t)&hot[0].a, sizeof(hot[0]), HOT_NODES, 0x314159, &expected[0].a);
  roots[0][1] = make_ring((uintptr_t)&hot[0].b, sizeof(hot[0]), HOT_NODES, 0x271828, &expected[0].b);
  roots[1][0] = make_ring((uintptr_t)&pressure[0].a, sizeof(pressure[0]), PRESSURE_NODES, 0x314159, &expected[1].a);
  roots[1][1] = make_ring((uintptr_t)&pressure[0].b, sizeof(pressure[0]), PRESSURE_NODES, 0x271828, &expected[1].b);
  /* Mixed cases retain one real pointer-walking handler, not an arithmetic
   * stand-in. Test both launch orders so a favorable first context is not
   * mistaken for general miss overlap. Data: 0=hot/hot, 1=pressure/pressure,
   * 2=pressure/hot, 3=hot/pressure (A/B). */
  roots[2][0] = roots[1][0]; roots[2][1] = roots[0][1];
  expected[2].a = expected[1].a; expected[2].b = expected[0].b;
  roots[3][0] = roots[0][0]; roots[3][1] = roots[1][1];
  expected[3].a = expected[0].a; expected[3].b = expected[1].b;
  bp_print_string("=== Independent Requests Benchmark (ordinary loads) ===\n");
  /* Warm all instruction paths, then execute each trial order and its reverse. */
  for (unsigned mode = 0; mode < 3; ++mode) {
    run(mode, roots[0][0], roots[0][1], HOT_NODES, &observed);
    if (observed.a != expected[0].a || observed.b != expected[0].b) goto fail;
  }
  for (unsigned data = 0; data < 4; ++data) {
    for (unsigned trial = 0; trial < 6; ++trial) {
      bp_print_string("[BSG-INFO] trial data/mode: ");
      bp_hprint_uint64(data * 16 + order[trial]); bp_print_string("\n");
      times[data][trial] = run(order[trial], roots[data][0], roots[data][1],
                              data ? PRESSURE_NODES : HOT_NODES, &observed);
      if (observed.a != expected[data].a || observed.b != expected[data].b) goto fail;
    }
  }
  bp_print_string("[BSG-INFO] chains/loads-per-chain: ");
  bp_hprint_uint64(2); bp_print_string(" "); bp_hprint_uint64(STEPS); bp_print_string("\n");
  for (unsigned data = 0; data < 4; ++data) {
    for (unsigned trial = 0; trial < 6; ++trial) {
      bp_print_string("[BSG-INFO] result data/mode/cycles: ");
      bp_hprint_uint64(data); bp_print_string(" ");
      bp_hprint_uint64(order[trial]); bp_print_string(" ");
      bp_hprint_uint64(times[data][trial]); bp_print_string("\n");
    }
  }
  bp_print_string("[BSG-PASS] both independent chain digests match in all modes\n");
  bp_finish(0);
  return 0;
fail:
  bp_print_string("[BSG-FAIL] independent chain digest mismatch\n");
  bp_hprint_uint64(observed.a); bp_print_string(" "); bp_hprint_uint64(observed.b);
  bp_print_string("\n");
  bp_finish(1);
  return 1;
}
