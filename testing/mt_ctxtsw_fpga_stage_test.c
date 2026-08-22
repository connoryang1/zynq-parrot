/**
 * mt_ctxtsw_fpga_stage_test.c
 *
 * Board-visible staged probe for resident and nonresident context switching.
 * Keep each stage to one pure-control round trip. Host MMIO is deliberately
 * kept outside the switches so the probe tests context handoff, not I/O drain.
 */

#include <stdint.h>

#include "bp_utils.h"
#include "mt_seed.h"

#define STACK_WORDS 256
static uint64_t t1_stack[STACK_WORDS];
static uint64_t t2_stack[STACK_WORDS];

static inline void raw_putc(char c) {
  *(volatile uint8_t *)0x00101000 = (uint8_t)c;
}
static inline void ctxtsw(unsigned int target) {
  /* Do not carry host-I/O or flag stores across the context boundary. */
  __asm__ volatile("fence rw, rw" ::: "memory");
  if (target == 0)
    __asm__ volatile("csrwi 0x081, 0" ::: "memory");
  else if (target == 1)
    __asm__ volatile("csrwi 0x081, 1" ::: "memory");
  else
    __asm__ volatile("csrwi 0x081, 2" ::: "memory");
}

void __attribute__((noinline, noreturn)) t1_entry(void) {
  __asm__ volatile("csrwi 0x081, 0" ::: "memory");
  for (;;)
    ;
}

void __attribute__((noinline, noreturn)) t2_entry(void) {
  __asm__ volatile("csrwi 0x081, 0" ::: "memory");
  for (;;)
    ;
}

int main(void) {
  seed_thread(1, &t1_stack[STACK_WORDS], (uint64_t)t1_entry);
  seed_thread(2, &t2_stack[STACK_WORDS], (uint64_t)t2_entry);

  ctxtsw(1);
  ctxtsw(2);

  raw_putc('P');
  raw_putc('\n');
  bp_finish(0);
  return 0;
}
