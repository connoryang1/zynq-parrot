/*
 * Equal-work latency-hiding benchmark: a dependent pointer walk and an
 * independent xorshift digest. Compare separate sequential loops, an explicitly
 * fused single-thread loop, and two resident contexts without prefetch opcodes.
 * Setup, cache preconditioning, result collection and printing are not timed.
 * This is a controlled synthetic workload, not an application speedup claim.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS < 2
#error "This benchmark needs two resident contexts"
#endif

#define STEPS 64
#define MIX_ROUNDS 8
#define HOT_NODES 8
#define SPARSE_NODES 128
#define STR1(x) #x
#define STR(x) STR1(x)

/* The sparse ring deliberately pressures eight D-cache sets: 16 lines/set
 * versus eight ways. State the 8 KiB touched/64 KiB span separately; this is
 * not a claim that uniformly distributed 8 KiB data exceeds a 32 KiB cache.
 */
struct hot_node { uintptr_t next; uint8_t pad[56]; };
struct sparse_node { uintptr_t next; uint8_t pad[504]; };
static struct hot_node hot[HOT_NODES] __attribute__((aligned(4096)));
static struct sparse_node sparse[SPARSE_NODES] __attribute__((aligned(4096)));
static uint64_t worker_stack[128];
static volatile uint64_t worker_result;

struct pair { uint64_t walk, compute; };

/* The exact same arithmetic appears in all three modes. Temporaries t2/t3
 * never depend on the outstanding pointer load (t0). Keep it register-only.
 */
#define MIX \
  ".rept " STR(MIX_ROUNDS) "\n" \
  "slli t2, a2, 13\nxor a2, a2, t2\n" \
  "srli t2, a2, 7\nxor a2, a2, t2\n" \
  "slli t2, a2, 17\nxor a2, a2, t2\n" \
  ".endr\n"
#define WALK_DIGEST \
  "slli t2, t1, 7\nsrli t3, t1, 57\nor t1, t2, t3\n" \
  "xor t1, t1, t0\nmv a0, t0\n"
#define ASM_BEGIN ".option push\n.option norvc\n"
#define ASM_END ".option pop\n"

uint64_t __attribute__((naked, noinline, aligned(64)))
walk_serial(uintptr_t root, uint64_t steps)
{
  __asm__ volatile(ASM_BEGIN
    "li t1, 0\n1:\nld t0, 0(a0)\n"
    WALK_DIGEST
    "addi a1, a1, -1\nbnez a1, 1b\nmv a0, t1\nret\n" ASM_END);
}

uint64_t __attribute__((naked, noinline, aligned(64)))
compute_serial(uint64_t steps)
{
  __asm__ volatile(ASM_BEGIN
    "mv a1, a0\nli a2, 1\n1:\n"
    MIX
    "addi a1, a1, -1\nbnez a1, 1b\nmv a0, a2\nret\n" ASM_END);
}

struct pair __attribute__((naked, noinline, aligned(64)))
walk_fused(uintptr_t root, uint64_t steps)
{
  __asm__ volatile(ASM_BEGIN
    "li t1, 0\nli a2, 1\n1:\nld t0, 0(a0)\n"
    MIX
    WALK_DIGEST
    "addi a1, a1, -1\nbnez a1, 1b\n"
    "mv a0, t1\nmv a1, a2\nret\n" ASM_END);
}

uint64_t __attribute__((naked, noinline, aligned(64)))
walk_switched(uintptr_t root, uint64_t steps)
{
  __asm__ volatile(ASM_BEGIN
    "li t1, 0\n1:\nld t0, 0(a0)\ncsrwi 0x800, 1\n"
    WALK_DIGEST
    "addi a1, a1, -1\nbnez a1, 1b\nmv a0, t1\nret\n" ASM_END);
}

void __attribute__((naked, noinline, noreturn, aligned(64))) compute_worker(void)
{
  __asm__ volatile(ASM_BEGIN
    "li a1, " STR(STEPS) "\nli a2, 1\n1:\n"
    MIX
    "addi a1, a1, -1\ncsrwi 0x800, 0\nbnez a1, 1b\n"
    /* The final timed switch has already completed all arithmetic. A separate
     * untimed switch resumes here to retrieve the result without a store
     * blocking behind the walk's last miss inside the measured interval. */
    "la t0, worker_result\nsd a2, 0(t0)\ncsrwi 0x800, 0\n"
    "2:\nj 2b\n" ASM_END);
}

static inline uint64_t cycle(void)
{
  uint64_t v;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(v) :: "memory");
  return v;
}

static uint64_t mix_reference(uint64_t x)
{
  x ^= x << 13;
  x ^= x >> 7;
  return x ^ (x << 17);
}

static uintptr_t make_ring(uintptr_t base, unsigned stride, unsigned count,
                           uint64_t *expected)
{
  unsigned order[SPARSE_NODES];
  uint64_t rng = 0x314159;
  for (unsigned i = 0; i < count; ++i)
    order[i] = i;
  for (unsigned i = count - 1; i; --i) {
    rng = mix_reference(rng);
    unsigned j = rng % (i + 1);
    unsigned t = order[i]; order[i] = order[j]; order[j] = t;
  }
  for (unsigned i = 0; i < count; ++i)
    *(uintptr_t *)(base + stride * order[i]) = base + stride * order[(i + 1) % count];
  /* Derive the expected walk digest from the permutation, not by touching
   * the ring under test. The rotation makes this sensitive to walk order. */
  *expected = 0;
  for (unsigned i = 0; i < STEPS; ++i) {
    *expected = (*expected << 7) | (*expected >> 57);
    *expected ^= base + stride * order[(i + 1) % count];
  }
  return base + stride * order[0];
}

/* mode 0: separate loops; mode 1: same-thread fused ideal reference;
 * mode 2: two independent resident register contexts. Context setup and final
 * result extraction are excluded; both useful digests finish before end. */
static uint64_t __attribute__((noinline))
run(unsigned mode, uintptr_t root, unsigned precondition_nodes, struct pair *result)
{
  struct pair value;
  if (mode == 2) {
    worker_result = 0;
    seed_thread(1, &worker_stack[128], (uint64_t)compute_worker);
  }
  /* Setup can touch a cache set; do it BEFORE the common preconditioning pass.
   * This tests steady cache pressure rather than assuming all misses hit DRAM. */
  (void)walk_serial(root, precondition_nodes);
  uint64_t begin = cycle();
  if (mode == 0) {
    value.walk = walk_serial(root, STEPS);
    value.compute = compute_serial(STEPS);
  } else if (mode == 1) {
    value = walk_fused(root, STEPS);
  } else {
    value.walk = walk_switched(root, STEPS);
  }
  uint64_t elapsed = cycle() - begin;
  if (mode == 2) {
    __asm__ volatile("csrwi 0x800, 1" ::: "memory");
    value.compute = worker_result;
  }
  *result = value;
  return elapsed;
}

int main(void)
{
  struct pair expected[2], observed;
  uintptr_t root[2];
  uint64_t times[2][6];
  const unsigned order[6] = {0, 1, 2, 2, 1, 0};
  root[0] = make_ring((uintptr_t)hot, sizeof(hot[0]), HOT_NODES, &expected[0].walk);
  root[1] = make_ring((uintptr_t)sparse, sizeof(sparse[0]), SPARSE_NODES, &expected[1].walk);
  uint64_t digest = 1;
  for (unsigned i = 0; i < STEPS * MIX_ROUNDS; ++i)
    digest = mix_reference(digest);
  expected[0].compute = expected[1].compute = digest;

  bp_print_string("=== Pointer + Compute Benchmark (no prefetch) ===\n");
  /* Prime every instruction path using the small ring before measurement. */
  for (unsigned mode = 0; mode < 3; ++mode) {
    run(mode, root[0], HOT_NODES, &observed);
    if (observed.walk != expected[0].walk || observed.compute != digest) {
      bp_print_string("[BSG-FAIL] warmup digest mismatch\n");
      bp_finish(1);
      return 1;
    }
  }
  for (unsigned data = 0; data < 2; ++data) {
    for (unsigned trial = 0; trial < 6; ++trial) {
      bp_print_string("[BSG-INFO] trial data/mode: ");
      bp_hprint_uint64(data * 16 + order[trial]);
      bp_print_string("\n");
      times[data][trial] = run(order[trial], root[data],
                               data ? SPARSE_NODES : HOT_NODES, &observed);
      if (observed.walk != expected[data].walk || observed.compute != digest) {
        bp_print_string("[BSG-FAIL] measured digest mismatch\n");
        bp_hprint_uint64(observed.walk); bp_hprint_uint64(expected[data].walk);
        bp_hprint_uint64(observed.compute); bp_hprint_uint64(digest);
        bp_finish(1);
        return 1;
      }
    }
  }
  bp_print_string("[BSG-INFO] steps/mix-rounds: ");
  bp_hprint_uint64(STEPS); bp_print_string(" ");
  bp_hprint_uint64(MIX_ROUNDS); bp_print_string("\n");
  for (unsigned data = 0; data < 2; ++data) {
    for (unsigned trial = 0; trial < 6; ++trial) {
      bp_print_string("[BSG-INFO] result data/mode/cycles: ");
      bp_hprint_uint64(data); bp_print_string(" ");
      bp_hprint_uint64(order[trial]); bp_print_string(" ");
      bp_hprint_uint64(times[data][trial]); bp_print_string("\n");
    }
  }
  bp_print_string("[BSG-PASS] all sequential/fused/resident digests match\n");
  bp_finish(0);
  return 0;
}
