/**
 * Shared body for the retained controlled-gap ctxtsw benchmark.
 *
 * Define CTXTSW_GAP_INSNS before including this file.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_seed.h"

#ifndef CTXTSW_GAP_INSNS
#error "CTXTSW_GAP_INSNS must be defined"
#endif

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn)) t_ping(void);

static inline void write_ctxt_1(void) {
  __asm__ volatile("csrwi 0x081, 1" ::: "memory");
}

static inline void write_ctxt_2(void) {
  __asm__ volatile("csrwi 0x081, 2" ::: "memory");
}

static inline void write_ctxt_3(void) {
  __asm__ volatile("csrwi 0x081, 3" ::: "memory");
}

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, cycle" : "=r"(v));
  return v;
}

static inline void restore_gp(void) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la gp, __global_pointer$\n"
    ".option pop\n"
    :
    :
    : "gp"
  );
}

static __attribute__((always_inline)) inline void controlled_gap(void) {
#if CTXTSW_GAP_INSNS != 8
#error "Only the retained gap8 benchmark is supported"
#endif
  __asm__ volatile(
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    "addi x0, x0, 0\n"
    ::: "memory"
  );
}

static inline uint64_t round_trip_once_1(void) {
  uint64_t before = read_cycle();
  write_ctxt_1();
  return read_cycle() - before;
}

static inline uint64_t round_trip_once_2(void) {
  uint64_t before = read_cycle();
  write_ctxt_2();
  return read_cycle() - before;
}

static inline uint64_t round_trip_once_3(void) {
  uint64_t before = read_cycle();
  write_ctxt_3();
  return read_cycle() - before;
}

static inline void seed_thread_to_ping(uint64_t tid, uint64_t *stack_top) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, (uint64_t)t_ping);
}

void __attribute__((naked, noinline, noreturn)) t_ping(void) {
  __asm__ volatile(
    "csrwi 0x081, 0\n"
    "1:\n"
    "j    1b\n"
  );
}

int main(void) {
  uint64_t cold, warm0, warm1;

  seed_thread_to_ping(1, &t1_stack[STACK_WORDS]);
  cold = round_trip_once_1();

  controlled_gap();
  seed_thread_to_ping(2, &t2_stack[STACK_WORDS]);
  warm0 = round_trip_once_2();

  controlled_gap();
  seed_thread_to_ping(3, &t3_stack[STACK_WORDS]);
  warm1 = round_trip_once_3();

  uint64_t warm_min = warm0;
  if (warm1 < warm_min)
    warm_min = warm1;

  restore_gp();
  bp_print_string("=== Context Switch Gap8 Benchmark ===\n");
  bp_print_string("Gap instructions: ");
  bp_hprint_uint64(CTXTSW_GAP_INSNS);
  bp_print_string("\nCold round-trip: ");
  bp_hprint_uint64(cold);
  bp_print_string(" cycles\nWarm round-trip 0: ");
  bp_hprint_uint64(warm0);
  bp_print_string(" cycles\nWarm round-trip 1: ");
  bp_hprint_uint64(warm1);
  bp_print_string(" cycles\nWarm min single-switch estimate: ");
  bp_hprint_uint64(warm_min / 2);
  bp_print_string(" cycles\n");

  bp_finish(0);
  return 0;
}
