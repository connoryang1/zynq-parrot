/* Remote register seeds share write ports with ordinary source writeback.
 * Check both source and resident target state across adjacent ALU, delayed
 * load/divide, and FP producers, consecutive seeds, and a seed with nonzero rd.
 * No timing NOPs separate a producer from its remote write.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Use two resident slots and four logical contexts"
#endif

#define SOURCE_CSR 0x2468ULL
#define INITIAL_T0 0x9000ULL
#define INITIAL_T1 0x9001ULL
#define ONE_BITS 0x3ff0000000000000ULL
#define ONE_HALF_BITS 0x3ff8000000000000ULL
#define TWO_BITS 0x4000000000000000ULL
#define THREE_BITS 0x4008000000000000ULL
#define INT_SEED(reg, value) \
  (((1ULL & BP_TID_MASK) << BP_TID_SHIFT) \
   | (((uint64_t)(reg) & BP_REG_MASK) << BP_REG_SHIFT) \
   | ((uint64_t)(value) & BP_VAL_MASK))
#define FP_ZERO_SEED (INT_SEED(0, 0) | (1ULL << BP_FP_SHIFT))

static uint64_t peer_stack[128] __attribute__((aligned(16)));
static volatile uint64_t target[4] __attribute__((used));
static volatile uint64_t source[3];
/* No earlier demand touches this line; the waveform establishes miss latency. */
static volatile uint64_t cold_line[8] __attribute__((aligned(64))) = {
  0x123456789abcdef0ULL
};

/* Read source context and CSR into the report before reading the producer's
 * result. These useful checks let its forwarding window expire, so a dropped
 * architectural write cannot be hidden by an immediate forwarded consumer.
 * The optional CSR802 rd is checked after the same interval.
 */
#define REPORT_SOURCE \
  "csrr a4, 0x800\nsd a4, 0(a3)\n" \
  "csrr a4, mscratch\nsd a4, 8(a3)\n" \
  "sd t1, 16(a3)\n"
#define KERNEL(name, body, result) \
static uint64_t __attribute__((naked, noinline)) name( \
    uint64_t seed __attribute__((unused)), uint64_t input __attribute__((unused)), \
    uint64_t aux __attribute__((unused)), volatile uint64_t *report __attribute__((unused))) \
{ __asm__ volatile( \
    ".option push\n.option norvc\nli t1, -1\n" \
    body REPORT_SOURCE result "\nret\n.option pop\n"); }

KERNEL(alu_seed, "mv t0, a1\ncsrw 0x802, a0\n", "mv a0, t0")
KERNEL(two_seeds, "mv t0, a1\ncsrw 0x802, a0\ncsrw 0x802, a2\n", "mv a0, t0")
KERNEL(seed_rd, "mv t0, a1\ncsrrw t1, 0x802, a0\n", "mv a0, t0")
KERNEL(two_seeds_rd, "mv t0, a1\ncsrrw t1, 0x802, a0\ncsrw 0x802, a2\n", "mv a0, t0")
KERNEL(load_seed, "ld t0, 0(a1)\ncsrw 0x802, a0\n", "mv a0, t0")
KERNEL(divide_seed, "divu t0, a1, a2\ncsrw 0x802, a0\n", "mv a0, t0")
KERNEL(fp_seed, "fmv.d.x ft1, a1\nfadd.d ft0, ft1, ft1\ncsrw 0x802, a0\n",
       "fmv.x.d a0, ft0")

static void __attribute__((naked, noinline, noreturn)) peer_entry(void)
{
  __asm__ volatile(
    "la t2, target\nsd t0, 0(t2)\nsd t1, 8(t2)\n"
    "fmv.x.d t0, ft0\nsd t0, 16(t2)\n"
    "csrr t0, 0x800\nsd t0, 24(t2)\n"
    /* Initialize a nonzero target FP value for the next trial, so a dropped
     * remote FP-zero seed cannot pass by observing reset zero. Raw recoded
     * zero is used for seeding; arbitrary IEEE bits are not a seed encoding.
     */
    "li t0, 0x3ff\nslli t0, t0, 52\nfmv.d.x ft0, t0\n"
    "fence rw, rw\ncsrwi 0x800, 0\n1: j 1b\n");
}

static void capture_target(void)
{
  target[3] = UINT64_MAX;
  seed_npc(1, (uint64_t)peer_entry);
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");
}

typedef uint64_t (*kernel_fn)(uint64_t, uint64_t, uint64_t, volatile uint64_t *);
struct trial {
  kernel_fn fn;
  uint64_t seed, input, aux, expected_source, expected_rd;
  uint64_t expected_t0, expected_t1, expected_fp;
};

int main(void)
{
  const struct trial cases[] = {
    {alu_seed, INT_SEED(5, 0x111), 0x123, 0, 0x123, UINT64_MAX,
     0x111, INITIAL_T1, ONE_BITS},
    {alu_seed, INT_SEED(6, 0x222), 0x456, 0, 0x456, UINT64_MAX,
     INITIAL_T0, 0x222, ONE_BITS},
    {two_seeds, INT_SEED(5, 0x333), 0x789, INT_SEED(6, 0x444), 0x789, UINT64_MAX,
     0x333, 0x444, ONE_BITS},
    {seed_rd, INT_SEED(5, 0x555), 0xabc, 0, 0xabc, 0,
     0x555, INITIAL_T1, ONE_BITS},
    {two_seeds_rd, INT_SEED(5, 0x666), 0xdef, INT_SEED(6, 0x777), 0xdef, 0,
     0x666, 0x777, ONE_BITS},
    {load_seed, INT_SEED(5, 0x888), (uint64_t)cold_line, 0,
     0x123456789abcdef0ULL, UINT64_MAX, 0x888, INITIAL_T1, ONE_BITS},
    {divide_seed, INT_SEED(6, 0x999), 0x123456789abcdef0ULL, 17,
     0x123456789abcdef0ULL / 17, UINT64_MAX, INITIAL_T0, 0x999, ONE_BITS},
    {fp_seed, INT_SEED(5, 0xaaa), ONE_HALF_BITS, 0, THREE_BITS, UINT64_MAX,
     0xaaa, INITIAL_T1, ONE_BITS},
    {fp_seed, FP_ZERO_SEED, ONE_BITS, 0, TWO_BITS, UINT64_MAX,
     INITIAL_T0, INITIAL_T1, 0}
  };
  unsigned stage = 0;
  uint64_t observed = 0, expected = 0;

  bp_print_string("[BSG-INFO] remote seed source/target writeback ordering\n");
#ifndef BP_FPGA_PROGRAM
  __asm__ volatile(
    "csrr t0, dcsr\nori t0, t0, 3\ncsrw dcsr, t0\n"
    "la t0, 1f\ncsrw dpc, t0\ndret\n1:" : : : "t0", "memory");
#endif
  __asm__ volatile("csrw mie, zero\ncsrw mscratch, %0\ncsrs mstatus, %1"
                   : : "r"(SOURCE_CSR), "r"(3ULL << 13) : "memory");
  seed_thread(1, &peer_stack[128], (uint64_t)peer_entry);
  seed_reg(1, 5, INITIAL_T0);
  seed_reg(1, 6, INITIAL_T1);
  seed_fp_reg(1, 0, 0);
  capture_target();
  if (target[0] != INITIAL_T0 || target[1] != INITIAL_T1
      || target[2] != 0 || target[3] != 1)
    goto fail;

  for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    const struct trial *c = &cases[i];
    stage = i + 1;
    seed_reg(1, 5, INITIAL_T0);
    seed_reg(1, 6, INITIAL_T1);
    source[0] = source[1] = source[2] = UINT64_MAX;
    observed = c->fn(c->seed, c->input, c->aux, source);
    expected = c->expected_source;
    capture_target();
    if (observed != expected || source[0] != 0 || source[1] != SOURCE_CSR
        || source[2] != c->expected_rd || target[0] != c->expected_t0
        || target[1] != c->expected_t1 || target[2] != c->expected_fp
        || target[3] != 1)
      goto fail;
  }
  bp_print_string("[BSG-PASS] remote seed source and target writeback ordering\n");
  bp_finish(0);
  return 0;
fail:
  bp_print_string("[BSG-FAIL] remote seed ordering stage/source/expected: ");
  bp_hprint_uint64(stage);
  bp_hprint_uint64(observed);
  bp_hprint_uint64(expected);
  bp_print_string("\nsource context/mscratch/CSR rd; target t0/t1/ft0/context: ");
  for (unsigned i = 0; i < 3; ++i) bp_hprint_uint64(source[i]);
  for (unsigned i = 0; i < 4; ++i) bp_hprint_uint64(target[i]);
  bp_print_string("\n");
  bp_finish(1);
  return 1;
}
