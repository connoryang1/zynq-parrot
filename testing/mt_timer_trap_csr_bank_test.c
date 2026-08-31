/**
 * Minimal machine-timer interrupt probe for the per-thread CSR bank.
 *
 * The handler records architectural state before calling any runtime code,
 * disables the timer source, and returns.  This separates timer delivery and
 * trap CSR correctness from the legacy timer test's printing/counting logic.
 */

#include <stdint.h>
#include "bp_utils.h"

#define MTIME_ADDR    0x0030bff8UL
#define MTIMECMP_ADDR 0x00304000UL
#define MIE_MTIE      (1UL << 7)
#define MSTATUS_MIE   (1UL << 3)

static volatile uint64_t *const mtime = (uint64_t *)MTIME_ADDR;
static volatile uint64_t *const mtimecmp = (uint64_t *)MTIMECMP_ADDR;

volatile uint64_t timer_trap_seen;
volatile uint64_t timer_trap_mcause;
volatile uint64_t timer_trap_mepc;
volatile uint64_t timer_trap_mtval;
volatile uint64_t timer_trap_mip;
volatile uint64_t timer_trap_mstatus;
volatile uint64_t timer_trap_context;

void __attribute__((interrupt, aligned(4))) timer_trap_entry(void) {
  __asm__ volatile("csrr %0, mcause" : "=r"(timer_trap_mcause));
  __asm__ volatile("csrr %0, mstatus" : "=r"(timer_trap_mstatus));
  *mtimecmp = UINT64_MAX;
  __asm__ volatile("csrr %0, mepc" : "=r"(timer_trap_mepc));
  __asm__ volatile("csrr %0, mtval" : "=r"(timer_trap_mtval));
  __asm__ volatile("csrr %0, mip" : "=r"(timer_trap_mip));
  __asm__ volatile("csrr %0, 0x800" : "=r"(timer_trap_context));

  __asm__ volatile("csrc mie, %0" : : "r"(MIE_MTIE) : "memory");
  timer_trap_seen = 1;
}

int main(void) {
  uintptr_t handler = (uintptr_t)timer_trap_entry;
  __asm__ volatile("csrw mtvec, %0" : : "r"(handler) : "memory");

  *mtimecmp = *mtime + 4096;
  __asm__ volatile("csrs mie, %0" : : "r"(MIE_MTIE) : "memory");
  __asm__ volatile("csrs mstatus, %0" : : "r"(MSTATUS_MIE) : "memory");

  while (!timer_trap_seen) {
    __asm__ volatile("nop");
  }

  bp_print_string("=== Machine Timer Trap CSR Bank Test ===\n");
  bp_print_string("mcause:       ");
  bp_hprint_uint64(timer_trap_mcause);
  bp_print_string("\nmepc:         ");
  bp_hprint_uint64(timer_trap_mepc);
  bp_print_string("\nmtval:        ");
  bp_hprint_uint64(timer_trap_mtval);
  bp_print_string("\nmip:          ");
  bp_hprint_uint64(timer_trap_mip);
  bp_print_string("\nmstatus:      ");
  bp_hprint_uint64(timer_trap_mstatus);
  bp_print_string("\ncontext:      ");
  bp_hprint_uint64(timer_trap_context);
  bp_print_string("\n");

  if ((timer_trap_mcause == ((1ULL << 63) | 7ULL))
      && (timer_trap_mtval == 0)
      && (timer_trap_context == 0)) {
    bp_print_string("[BSG-PASS] machine timer trap CSR bank verified\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] machine timer trap CSR bank mismatch\n");
    bp_finish(1);
  }

  return 0;
}
