/**
 * Verify that custom CSR 0xCC0 is a monotonic physical cycle counter and is
 * not virtualized by resident or nonresident context save/restore.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256

static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];
static volatile uint64_t resident_target_cycle;
static volatile uint64_t nonresident_target_cycle;

static inline uint64_t read_global_cycle(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, 0xcc0" : "=r"(value) :: "memory");
  return value;
}

static inline uint64_t read_time(void) {
  uint64_t value;
  __asm__ volatile("rdtime %0" : "=r"(value) :: "memory");
  return value;
}

static inline void switch_to(unsigned int context_id) {
  if (context_id == 0)
    __asm__ volatile("csrwi 0x081, 0" ::: "memory");
  else if (context_id == 1)
    __asm__ volatile("csrwi 0x081, 1" ::: "memory");
  else
    __asm__ volatile("csrwi 0x081, 2" ::: "memory");
}

void __attribute__((noinline, noreturn)) resident_entry(void) {
  resident_target_cycle = read_global_cycle();
  switch_to(0);
  for (;;)
    ;
}

void __attribute__((noinline, noreturn)) nonresident_entry(void) {
  nonresident_target_cycle = read_global_cycle();
  switch_to(0);
  for (;;)
    ;
}

static int check_order(const char *name, uint64_t before, uint64_t target, uint64_t after) {
  if (!(before < target && target < after)) {
    bp_print_string("[BSG-FAIL] ");
    bp_print_string(name);
    bp_print_string(" global cycle was not monotonic\n");
    return 1;
  }
  return 0;
}

int main(void) {
  uint64_t first = read_global_cycle();
  uint64_t second = read_global_cycle();
  if (second <= first) {
    bp_print_string("[BSG-FAIL] global cycle did not advance\n");
    bp_finish(1);
    return 1;
  }
  uint64_t time_first = read_time();
  uint64_t time_second = read_time();
  if (time_second <= time_first) {
    bp_print_string("[BSG-FAIL] standard time CSR did not advance\n");
    bp_finish(1);
    return 1;
  }

  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)resident_entry);
  uint64_t resident_before = read_global_cycle();
  switch_to(1);
  uint64_t resident_after = read_global_cycle();
  if (check_order("resident switch", resident_before, resident_target_cycle, resident_after)) {
    bp_finish(1);
    return 1;
  }

  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)nonresident_entry);
  uint64_t nonresident_before = read_global_cycle();
  switch_to(2);
  uint64_t nonresident_after = read_global_cycle();
  if (check_order("nonresident switch", nonresident_before, nonresident_target_cycle,
                  nonresident_after)) {
    bp_finish(1);
    return 1;
  }

  bp_print_string("[BSG-INFO] resident global cycles: ");
  bp_hprint_uint64(resident_after - resident_before);
  bp_print_string("\n[BSG-INFO] nonresident global cycles: ");
  bp_hprint_uint64(nonresident_after - nonresident_before);
  bp_print_string("\n[BSG-PASS] global cycle remains monotonic across context switches\n");
  bp_finish(0);
  return 0;
}
