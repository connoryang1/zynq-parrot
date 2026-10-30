/*
 * Measure the instruction-cache cold-start component of a nonresident resume.
 * Modes 0-3 are cold, target-warmup, source-warm, and switch-only controls.
 * The target warmup runs outside the timed interval; it does not guarantee
 * that the target lines remain in the I-cache through source-side setup.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define PREFIX_OPS 96

#define REP2(op) op op
#define REP4(op) REP2(op) REP2(op)
#define REP8(op) REP4(op) REP4(op)
#define REP16(op) REP8(op) REP8(op)
#define REP32(op) REP16(op) REP16(op)
#define REP64(op) REP32(op) REP32(op)
#define REP96(op) REP64(op) REP32(op)

static uint64_t target_stack[STACK_WORDS];
static volatile uint64_t peer_done __attribute__((aligned(8)));
static volatile uint64_t prefix_sink __attribute__((aligned(8)));
static volatile uint64_t warmup_gate;
/* Keep this in .data so the simulator's post-load runtime patch survives CRT
 * BSS clearing and selects the requested mode deterministically. */
volatile uint64_t benchmark_mode __attribute__((used, aligned(8))) = UINT64_MAX;

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

/* Keep the prefix in a distinct, aligned text region for a stable footprint. */
static void __attribute__((noinline, aligned(4096), section(".text.resume_target")))
resume_prefix(void)
{
  __asm__ volatile(
    ".option push\n.option norvc\n"
    "li t0, 0\n"
    REP96("addi t0, t0, 1\n")
    "la t1, prefix_sink\n"
    "sd t0, 0(t1)\n"
    ".option pop\n"
    : : : "t0", "t1", "memory");
}

void __attribute__((noinline, aligned(8))) target_entry(void)
{
  if (benchmark_mode != 3)
    resume_prefix();
  else
    prefix_sink = PREFIX_OPS;
  if (warmup_gate) {
    peer_done = 0xfeed;
    if (warmup_gate == 1) {
      __asm__ volatile("fence rw, rw\ncsrwi 0x800, 0\n" : : : "memory");
      for (;;) { }
    }
    return;
  }

  peer_done = 2;
  __asm__ volatile("fence rw, rw\ncsrwi 0x800, 0\n" : : : "memory");
  for (;;) { }
}

static void __attribute__((noinline, aligned(8))) source_entry(void)
{
  uint64_t begin;
  uint64_t cycles;
  uint64_t mode = benchmark_mode;

  seed_thread(2, &target_stack[STACK_WORDS], (uint64_t)target_entry);
  /* Warm/oracle execution is outside the measured interval. */
  if (mode == 1) {
    warmup_gate = 1;
    __asm__ volatile("csrwi 0x800, 2\n" : : : "memory");
    warmup_gate = 0;
    peer_done = 0;
    seed_thread(2, &target_stack[STACK_WORDS], (uint64_t)target_entry);
  } else if (mode == 2) {
    warmup_gate = 2;
    target_entry();
    warmup_gate = 0;
    peer_done = 0;
    seed_thread(2, &target_stack[STACK_WORDS], (uint64_t)target_entry);
  }

  begin = read_global_cycle();
  __asm__ volatile("csrwi 0x800, 2\n" : : : "memory");
  cycles = read_global_cycle() - begin;

  if (peer_done != 2) {
    bp_print_string("[BSG-FAIL] context-resume target completion missing\n");
    bp_finish(1);
    return;
  }

  bp_print_string("=== Context Resume Instruction Prefix Benchmark ===\n");
  bp_print_string("Mode: ");
  bp_hprint_uint64(mode);
  bp_print_string("\nPrefix operations:              ");
  bp_hprint_uint64(PREFIX_OPS);
  bp_print_string("\nResume cycles:                  ");
  bp_hprint_uint64(cycles);
  bp_print_string("\nPrefix checksum:                ");
  bp_hprint_uint64(prefix_sink);
  bp_print_string("\n[BSG-PASS] matched context-resume prefix benchmark\n");
  bp_finish(0);
  for (;;) { }
}

int main(void)
{
  source_entry();
  return 0;
}
