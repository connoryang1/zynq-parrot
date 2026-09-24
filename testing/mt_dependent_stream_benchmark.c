/* Compare serial and interleaved traversal of independent dependent chains.
 * Each next address is loaded from its current cold 64-byte node. The fixed
 * aggregate workload visits 1280 nodes (80 KiB); no guest initialization or
 * warmup traverses the measured graph. All schedules publish complete results
 * and finish a common fence before the physical-cycle ending timestamp.
 */
#include <stdint.h>
#include "bp_utils.h"
#include "bp_prefetch.h"
#include "mt_seed.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 10
#error "Use NUM_THREADS=2 NUM_CONTEXTS=10 for the fixed FPGA image"
#endif

struct node { const volatile struct node *next; uint64_t value, pad[6]; };
_Static_assert(sizeof(struct node) == 64, "one node per cache line");
#include "dependent_stream_data.h"

/* One host-patched word: mode bits7:0, streams bits15:8, total nodes bits31:16.
 * It lives in initialized data, never CRT-zeroed BSS. */
volatile uint64_t benchmark_config __attribute__((section(".data"))) =
  UINT64_C(3) | (UINT64_C(4) << 8) | (UINT64_C(1280) << 16);

struct result { uint64_t sum, count, cursor, done; };
static volatile struct result results[4] __attribute__((aligned(64)));

#define ASM_BEGIN ".option push\n.option norvc\n"
#define ASM_END "ret\n.option pop\n"
#define PUBLISH(sum, count, cursor, output) \
  "sd " sum ", 0(" output ")\nsd " count ", 8(" output ")\n" \
  "sd " cursor ", 16(" output ")\nli a7, 1\nsd a7, 24(" output ")\n"

/* Serial variants use the same traversal, checksum and terminal publication.
 * A prefetched successor is requested immediately after its address is known.
 * The last node has no successor hint, so no unconsumed detached fill remains.
 */
#define DEFINE_SERIAL(name, prime, successor_hint) \
static __attribute__((naked, noinline, aligned(64))) void name \
  (const volatile struct node *cursor, volatile struct result *out, uint64_t steps) \
{ \
  __asm__ volatile(ASM_BEGIN \
    "mv a3, a2\nli a4, 0\n" prime \
    "1: ld t0, 0(a0)\naddi a2, a2, -1\n" successor_hint \
    "ld t1, 8(a0)\nadd a4, a4, t1\nmv a0, t0\nbnez a2, 1b\n" \
    PUBLISH("a4", "a3", "a0", "a1") ASM_END); \
}
DEFINE_SERIAL(serial_demand, "", "")
DEFINE_SERIAL(serial_prefetch, BP_PREFETCH_R_ASM("a0"),
              "beqz a2, 2f\n" BP_PREFETCH_R_ASM("t0") "2:\n")

/* Each context runs the same leaf, using only caller-saved registers. The
 * initial hint/yield primes the ring. After the last node, each participant
 * publishes before its final yield. Context zero returns only after the last
 * peer's final yield completes that lap; peers then remain parked.
 */
static __attribute__((naked, noinline, aligned(64))) void hardware_worker
  (const volatile struct node *cursor, volatile struct result *out,
   uint64_t steps, uint64_t next_context, uint64_t park)
{
  __asm__ volatile(ASM_BEGIN
    "mv a5, a2\nli a6, 0\n" BP_PREFETCH_R_ASM("a0")
    "csrw 0x800, a3\n"
    "1: ld t0, 0(a0)\naddi a2, a2, -1\nbeqz a2, 2f\n"
    BP_PREFETCH_R_ASM("t0")
    "2: ld t1, 8(a0)\nadd a6, a6, t1\nmv a0, t0\nbeqz a2, 3f\n"
    "csrw 0x800, a3\nj 1b\n"
    "3:\n" PUBLISH("a6", "a5", "a0", "a1")
    "csrw 0x800, a3\nbeqz a4, 5f\n4: j 4b\n5:\n" ASM_END);
}

/* Software keeps every cursor/checksum in registers, exposing independent
 * work without state-array loads/stores in the hot loop. Shared remaining
 * count is decremented once per lap. No hint is issued on the final lap.
 */
#define SW_NODE(cursor, sum) \
  "ld a5, 0(" cursor ")\nbeqz a2, 2f\n" BP_PREFETCH_R_ASM("a5") \
  "2: ld a6, 8(" cursor ")\nadd " sum ", " sum ", a6\nmv " cursor ", a5\n"
#define SW_PUBLISH(cursor, sum) \
  PUBLISH(sum, "a4", cursor, "a1") "addi a1, a1, 32\n"
static __attribute__((naked, noinline, aligned(64))) void software_two
  (const volatile struct node *const *heads, volatile struct result *out,
   uint64_t steps)
{
  __asm__ volatile(ASM_BEGIN
    "ld t0, 0(a0)\nld t1, 8(a0)\nli t4, 0\nli t5, 0\nmv a4, a2\n"
    BP_PREFETCH_R_ASM("t0") BP_PREFETCH_R_ASM("t1")
    "1: addi a2, a2, -1\n" SW_NODE("t0", "t4") SW_NODE("t1", "t5")
    "bnez a2, 1b\n" SW_PUBLISH("t0", "t4") SW_PUBLISH("t1", "t5") ASM_END);
}
static __attribute__((naked, noinline, aligned(64))) void software_four
  (const volatile struct node *const *heads, volatile struct result *out,
   uint64_t steps)
{
  __asm__ volatile(ASM_BEGIN
    "ld t0, 0(a0)\nld t1, 8(a0)\nld t2, 16(a0)\nld t3, 24(a0)\n"
    "li t4, 0\nli t5, 0\nli t6, 0\nli a3, 0\nmv a4, a2\n"
    BP_PREFETCH_R_ASM("t0") BP_PREFETCH_R_ASM("t1")
    BP_PREFETCH_R_ASM("t2") BP_PREFETCH_R_ASM("t3")
    "1: addi a2, a2, -1\n"
    SW_NODE("t0", "t4") SW_NODE("t1", "t5") SW_NODE("t2", "t6") SW_NODE("t3", "a3")
    "bnez a2, 1b\n"
    SW_PUBLISH("t0", "t4") SW_PUBLISH("t1", "t5") SW_PUBLISH("t2", "t6") SW_PUBLISH("t3", "a3") ASM_END);
}

static void prepare(const volatile struct node *const *heads, unsigned streams,
                    uint64_t steps)
{
  for (unsigned i = 0; i < 4; ++i) {
    results[i].sum = results[i].count = results[i].cursor = results[i].done = 0;
  }
  /* Setup is common even for software/serial modes and is outside timing. */
  for (unsigned i = 1; i < streams; ++i) {
    seed_reg(i, 10, (uint64_t)heads[i]);
    seed_reg(i, 11, (uint64_t)&results[i]);
    seed_reg(i, 12, steps);
    seed_reg(i, 13, (i + 1) % streams);
    seed_reg(i, 14, 1);
    seed_npc(i, (uint64_t)hardware_worker);
    __asm__ volatile("fence rw, rw" ::: "memory");
  }
}

static __attribute__((noinline, used)) void run_operation
  (unsigned mode, const volatile struct node *const *heads,
   volatile struct result *out, uint64_t steps, unsigned streams)
{
  if (mode < 2) {
    for (unsigned i = 0; i < streams; ++i) {
      if (mode == 0) serial_demand(heads[i], &out[i], steps);
      else serial_prefetch(heads[i], &out[i], steps);
    }
  } else if (mode == 2) {
    if (streams == 2) software_two(heads, out, steps);
    else software_four(heads, out, steps);
  } else {
    hardware_worker(heads[0], out, steps, 1, 0);
  }
}

/* Keep the physical timestamp in ABI-preserved s0 across ordinary C calls
 * and context-zero's full architectural save/restore. Stack traffic for this
 * wrapper is outside timing. Priming, dispatch, publication and the final
 * fence are inside every measured interval.
 */
static __attribute__((naked, noinline, aligned(64))) uint64_t run_window
  (unsigned mode, const volatile struct node *const *heads,
   volatile struct result *out, uint64_t steps, unsigned streams)
{
  __asm__ volatile(ASM_BEGIN
    "addi sp, sp, -16\nsd ra, 0(sp)\nsd s0, 8(sp)\nfence rw, rw\n"
    "csrr s0, 0xcc0\ncall run_operation\nfence rw, rw\ncsrr a0, 0xcc0\n"
    "sub a0, a0, s0\nld ra, 0(sp)\nld s0, 8(sp)\naddi sp, sp, 16\n" ASM_END);
}

static void check_results(unsigned streams, uint64_t steps, unsigned warm)
{
  for (unsigned i = 0; i < streams; ++i) {
    uint64_t graph_nodes = warm ? 16 : STREAM_DATA_NODES;
    uint64_t first = i * (graph_nodes / streams);
    uint64_t expected_sum = steps * (first + 1) + steps * (steps - 1) / 2;
    uint64_t final = (first + steps) % graph_nodes;
    const volatile struct node *expected_cursor = warm ? &warm_nodes[final] : expected_cursors[final];
    if (results[i].sum != expected_sum || results[i].count != steps
        || results[i].cursor != (uint64_t)expected_cursor || results[i].done != 1) {
      bp_print_string("[BSG-FAIL] dependent stream result mismatch; stream=");
      bp_hprint_uint64(i);
      bp_print_string("\n");
      bp_finish(1);
    }
  }
}

int main(void)
{
  uint64_t config = benchmark_config;
  unsigned mode = config & 255, streams = (config >> 8) & 255;
  uint64_t nodes = (config >> 16) & 65535;
  if ((config >> 32) || mode > 3 || (streams != 2 && streams != 4) || !nodes
      || nodes > 1280 || nodes % streams) {
    bp_print_string("[BSG-FAIL] dependent stream runtime configuration\n");
    bp_finish(1);
  }
  uint64_t steps = nodes / streams;
  const volatile struct node *const *warm_heads = streams == 2 ? warm_heads_2 : warm_heads_4;
  const volatile struct node *const *measured_heads = streams == 2 ? measured_heads_2 : measured_heads_4;
  for (unsigned warm_mode = 0; warm_mode < 4; ++warm_mode) {
    prepare(warm_heads, streams, 4);
    run_window(warm_mode, warm_heads, results, 4, streams);
    check_results(streams, 4, 1);
  }
  prepare(measured_heads, streams, steps);
  uint64_t cycles = run_window(mode, measured_heads, results, steps, streams);
  check_results(streams, steps, 0);
  bp_print_string("Benchmark: DEPENDENT mode="); bp_hprint_uint64(mode);
  bp_print_string(" streams="); bp_hprint_uint64(streams);
  bp_print_string(" nodes="); bp_hprint_uint64(nodes);
  bp_print_string(" cycles="); bp_hprint_uint64(cycles);
  bp_print_string("\n[BSG-PASS] dependent streams, checksums and completion\n");
  bp_finish(0);
  return 0;
}
