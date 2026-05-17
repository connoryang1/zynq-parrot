/**
 * mt_ctxtsw_microbench_trace.c
 *
 * Diagnostic version of mt_ctxtsw_microbench.
 *
 * It preserves the original benchmark shape, but prints progress before and
 * after each seed/switch step so a long run or hang can be localized.
 */

#include <stdint.h>
#include "bp_utils.h"

#define STACK_WORDS 512

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static uint64_t t3_stack[STACK_WORDS];

void __attribute__((naked, noinline, noreturn)) t_ping(void);

static inline void marker(char *s) {
  __asm__ volatile(
    ".option push\n"
    ".option norelax\n"
    "la gp, __global_pointer$\n"
    ".option pop\n"
    :
    :
    : "gp"
  );
  bp_print_string(s);
  bp_print_string("\n");
}

static inline void write_ctxt_1(void) {
  __asm__ volatile("csrwi 0x081, 1" ::: "memory");
}

static inline void write_ctxt_2(void) {
  __asm__ volatile("csrwi 0x081, 2" ::: "memory");
}

static inline void write_ctxt_3(void) {
  __asm__ volatile("csrwi 0x081, 3" ::: "memory");
}

static inline void seed_npc(uint64_t tid, uint64_t npc) {
  uint64_t v = ((tid & 0x3ULL) << 39) | (npc & 0x7FFFFFFFFFULL);
  __asm__ volatile("csrw 0x082, %0" : : "r"(v) : "memory");
}

static inline void seed_reg(uint64_t tid, uint64_t reg, uint64_t val) {
  uint64_t v = (val & 0x7FFFFFFFFFULL)
             | ((tid & 0x3ULL) << 39)
             | ((reg & 0x1FULL) << 41);
  __asm__ volatile("csrw 0x083, %0" : : "r"(v) : "memory");
}

static inline uint64_t read_cycle(void) {
  uint64_t v;
  __asm__ volatile("csrr %0, cycle" : "=r"(v));
  return v;
}

static inline void seed_thread(uint64_t tid, uint64_t *stack_top) {
  uint64_t gp_val;
  __asm__ volatile("mv %0, gp" : "=r"(gp_val));

  seed_reg(tid, 3 /* x3=gp */, gp_val);
  seed_reg(tid, 2 /* x2=sp */, (uint64_t)stack_top);
  seed_npc(tid, (uint64_t)t_ping);
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

void __attribute__((naked, noinline, noreturn)) t_ping(void) {
  __asm__ volatile(
    "csrwi 0x081, 0\n"
    "1:\n"
    "j    1b\n"
  );
}

int main(void) {
  uint64_t cold, warm0, warm1;

  marker("trace: start");

  marker("trace: seed 1 begin");
  seed_thread(1, &t1_stack[STACK_WORDS]);
  marker("trace: seed 1 done");
  marker("trace: switch 1 begin");
  cold = round_trip_once_1();
  marker("trace: switch 1 done");

  marker("trace: seed 2 begin");
  seed_thread(2, &t2_stack[STACK_WORDS]);
  marker("trace: seed 2 done");
  marker("trace: switch 2 begin");
  warm0 = round_trip_once_2();
  marker("trace: switch 2 done");

  marker("trace: seed 3 begin");
  seed_thread(3, &t3_stack[STACK_WORDS]);
  marker("trace: seed 3 done");
  marker("trace: switch 3 begin");
  warm1 = round_trip_once_3();
  marker("trace: switch 3 done");

  marker("trace: results begin");
  bp_print_string("cold: ");
  bp_hprint_uint64(cold);
  bp_print_string("\n");
  bp_print_string("warm0: ");
  bp_hprint_uint64(warm0);
  bp_print_string("\n");
  bp_print_string("warm1: ");
  bp_hprint_uint64(warm1);
  bp_print_string("\n");
  marker("trace: pass");

  bp_finish(0);
  return 0;
}
