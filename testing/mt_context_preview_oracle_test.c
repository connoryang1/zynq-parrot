/* Measure a bounded target-context data preview before the real handoff.
 * The target issues oracle hints, returns to the source, and later consumes
 * the same lines. Direct, empty, and stale previews expose control overhead.
 */
#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"
#include "bp_prefetch.h"

#if BP_NUM_THREADS != 2 || BP_NUM_CONTEXTS != 4
#error "Context preview oracle requires two resident slots and four contexts"
#endif

struct line { uint64_t word[8]; };
static const volatile struct line target_lines[4]
  __attribute__((aligned(4096), used)) = {
    {{0x100}}, {{0x101}}, {{0x102}}, {{0x103}}
  };
static const volatile struct line stale_lines[4]
  __attribute__((aligned(4096), used)) = {
    {{0x200}}, {{0x201}}, {{0x202}}, {{0x203}}
  };
static const volatile unsigned char eviction[10 * 4096]
  __attribute__((aligned(4096), used)) = {1};
static volatile uint64_t result[3] __attribute__((aligned(64), used));
static volatile uint64_t eviction_sink;

/* a0=target lines, a1=result, a2=mode, a3=stale lines.
 * Modes: 0 direct; 1 empty preview; 2 correct preview; 3 stale preview.
 * The saved NPC after the first switch is the demand entry at label 3.
 */
static void __attribute__((naked, noinline, noreturn, used, aligned(64)))
target(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n.option norelax\n"
    "beqz a2, 3f\n"
    "li t2, 1\nbeq a2, t2, 2f\n"
    "mv t0, a0\n"
    "li t2, 3\nbne a2, t2, 1f\nmv t0, a3\n"
    "1:\n"
    BP_PREFETCH_R_ASM("t0")
    "addi t0, t0, 64\n"
    BP_PREFETCH_R_ASM("t0")
    "addi t0, t0, 64\n"
    BP_PREFETCH_R_ASM("t0")
    "addi t0, t0, 64\n"
    BP_PREFETCH_R_ASM("t0")
    "2:\nli t2, 1\nsd t2, 0(a1)\nfence rw, rw\n"
    "csrwi 0x800, 0\n"
    "3:\nli t3, 0\n"
    "ld t1, 0(a0)\nadd t3, t3, t1\n"
    "ld t1, 64(a0)\nadd t3, t3, t1\n"
    "ld t1, 128(a0)\nadd t3, t3, t1\n"
    "ld t1, 192(a0)\nadd t3, t3, t1\n"
    "sd t3, 8(a1)\ncsrr t2, 0x800\nsd t2, 16(a1)\n"
    "fence rw, rw\ncsrwi 0x800, 0\n"
    "4: j 4b\n.option pop\n"
    ::: "memory");
}

static uint64_t global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) : : "memory");
  return value;
}

static void source_work(void)
{
  __asm__ volatile(
    "li t0, 128\n"
    "1: addi t0, t0, -1\nbnez t0, 1b\n"
    : : : "t0", "memory");
}

static void prepare_cold_lines(void)
{
  uint64_t sum = 0;
  for (unsigned i = 0; i < 4; ++i)
    sum += target_lines[i].word[0];
  for (unsigned page = 0; page < 10; ++page)
    for (unsigned set = 0; set < 4; ++set)
      sum += eviction[page * 4096 + set * 64];
  eviction_sink = sum;
  __asm__ volatile("fence rw, rw" : : : "memory");
}

static int run_mode(unsigned mode, unsigned repeat)
{
  prepare_cold_lines();
  for (unsigned i = 0; i < 3; ++i) result[i] = 0;
  seed_reg(1, 10, (uint64_t)target_lines);
  seed_reg(1, 11, (uint64_t)result);
  seed_reg(1, 12, mode);
  seed_reg(1, 13, (uint64_t)stale_lines);
  seed_npc(1, (uint64_t)target);
  __asm__ volatile("fence rw, rw" : : : "memory");

  uint64_t begin = global_cycle();
  if (mode != 0) {
    __asm__ volatile("csrwi 0x800, 1" : : : "memory");
    if (result[0] != 1) return 0;
  }
  source_work();
  __asm__ volatile("csrwi 0x800, 1" : : : "memory");
  uint64_t cycles = global_cycle() - begin;

  /* Results follow repeat-major, then mode 0..3 order. Keep serial output
   * short enough that the simulator heartbeat cannot split the PASS marker. */
  bp_print_string("Preview cycles: ");
  bp_hprint_uint64(cycles);
  bp_print_string("\n");
  return result[1] == 0x406 && result[2] == 1;
}

int main(void)
{
  for (unsigned repeat = 0; repeat < 3; ++repeat)
    for (unsigned mode = 0; mode < 4; ++mode)
      if (!run_mode(mode, repeat)) {
        bp_print_string("[BSG-FAIL] context preview oracle result\n");
        bp_finish(1);
        return 1;
      }
  bp_print_string("[BSG-PASS] context preview oracle handoff and data\n");
  bp_finish(0);
  return 0;
}
