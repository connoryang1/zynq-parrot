/**
 * Measure the conditional cost of draining a hot store immediately before a
 * resident or nonresident context switch.  Pure and store-bearing rings run
 * in the same image against the same global cycle counter.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 512
#define SWITCHES_PER_CONTEXT 128
#define UNROLL_FACTOR 32
#define LOOP_ITERS (SWITCHES_PER_CONTEXT / UNROLL_FACTOR)
#define TOTAL_SWITCHES (2 * SWITCHES_PER_CONTEXT)

#define REP2(op)  op op
#define REP4(op)  REP2(op) REP2(op)
#define REP8(op)  REP4(op) REP4(op)
#define REP16(op) REP8(op) REP8(op)
#define REP32(op) REP16(op) REP16(op)
#define STR2(x) #x
#define STR(x) STR2(x)

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static volatile uint64_t peer_contexts[4] __attribute__((used, aligned(8)));
static volatile uint64_t store_sinks[3] __attribute__((used, aligned(64)));

#define RECORD_COMPLETION(offset) \
    "la t0, peer_contexts\n" \
    "csrr t1, 0x800\n" \
    "sd t1, " offset "(t0)\n" \
    "fence rw, rw\n" \
    "csrwi 0x800, 0\n"

static inline uint64_t read_global_cycle(void)
{
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

#define SOURCE_RING(name, target, operation, setup) \
static void __attribute__((noinline, aligned(8))) name(void) \
{ \
  __asm__ volatile( \
    ".option push\n.option norvc\n" setup \
    "li t0, " STR(LOOP_ITERS) "\n1:\n" \
    REP32(operation "csrwi 0x800, " #target "\n") \
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n" \
    : : : "t0", "t1", "memory"); \
}

#define PEER_RING(name, target, operation, setup, completion_offset) \
void __attribute__((noinline, noreturn, aligned(8))) name(void) \
{ \
  __asm__ volatile( \
    ".option push\n.option norvc\n" setup \
    "li t0, " STR(LOOP_ITERS) "\n1:\n" \
    REP32(operation "csrwi 0x800, " #target "\n") \
    "addi t0, t0, -1\nbnez t0, 1b\n.option pop\n" \
    : : : "t0", "t1", "memory"); \
  __asm__ volatile(RECORD_COMPLETION(completion_offset) \
                   : : : "t0", "t1", "memory"); \
  for (;;) ; \
}

SOURCE_RING(t0_warm_pure, 1, "", "")
PEER_RING(t1_warm_pure, 0, "", "", "0")
SOURCE_RING(t0_cold_pure, 2, "", "")
PEER_RING(t2_cold_pure, 0, "", "", "8")

SOURCE_RING(t0_warm_store, 1, "sd t0, 0(t1)\n",
            "la t1, store_sinks\n")
PEER_RING(t1_warm_store, 0, "sd t0, 0(t1)\n",
          "la t1, store_sinks\naddi t1, t1, 8\n", "16")
SOURCE_RING(t0_cold_store, 2, "sd t0, 0(t1)\n",
            "la t1, store_sinks\n")
PEER_RING(t2_cold_store, 0, "sd t0, 0(t1)\n",
          "la t1, store_sinks\naddi t1, t1, 16\n", "24")

static uint64_t run_ring(unsigned context, uint64_t *stack,
                         void (*source)(void), void (*peer)(void))
{
  seed_thread(context, &stack[STACK_WORDS], (uint64_t)peer);
  source();
  seed_thread(context, &stack[STACK_WORDS], (uint64_t)peer);
  uint64_t begin = read_global_cycle();
  source();
  uint64_t cycles = read_global_cycle() - begin;
  if (context == 1)
    __asm__ volatile("csrwi 0x800, 1" : : : "memory");
  else
    __asm__ volatile("csrwi 0x800, 2" : : : "memory");
  return cycles;
}

static void print_x100(char *label, uint64_t cycles)
{
  bp_print_string(label);
  bp_hprint_uint64((cycles * 100) / TOTAL_SWITCHES);
  bp_print_string("\n");
}

int main(void)
{
  uint64_t warm_pure = run_ring(1, t1_stack, t0_warm_pure, t1_warm_pure);
  uint64_t cold_pure = run_ring(2, t2_stack, t0_cold_pure, t2_cold_pure);
  uint64_t warm_store = run_ring(1, t1_stack, t0_warm_store, t1_warm_store);
  uint64_t cold_store = run_ring(2, t2_stack, t0_cold_store, t2_cold_store);

  if (peer_contexts[0] != 1 || peer_contexts[1] != 2
      || peer_contexts[2] != 1 || peer_contexts[3] != 2
      || store_sinks[0] == 0 || store_sinks[1] == 0 || store_sinks[2] == 0) {
    bp_print_string("[BSG-FAIL] store-handoff completion missing\n");
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-PASS] matched store-before-switch handoff benchmark\n");
  bp_print_string("=== Store-before-switch Handoff Benchmark ===\n");
  print_x100("Resident pure cycles/switch x100:       ", warm_pure);
  print_x100("Resident store cycles/switch x100:      ", warm_store);
  print_x100("Resident store overhead/switch x100:    ", warm_store - warm_pure);
  print_x100("Nonresident pure cycles/switch x100:    ", cold_pure);
  print_x100("Nonresident store cycles/switch x100:   ", cold_store);
  print_x100("Nonresident store overhead/switch x100: ", cold_store - cold_pure);
  bp_finish(0);
  return 0;
}
