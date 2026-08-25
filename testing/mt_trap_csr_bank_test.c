/**
 * Verify that a synchronous trap updates and exposes the CSR bank belonging
 * to the interrupted hardware thread.
 *
 * An M-mode ECALL is deterministic and does not depend on the timer bridge.
 * The handler records the trap CSRs, advances MEPC past the ECALL, and returns.
 */

#include <stdint.h>
#include "bp_utils.h"

volatile uint64_t trap_seen;
volatile uint64_t trap_mcause;
volatile uint64_t trap_mepc;
volatile uint64_t trap_mtval;
volatile uint64_t trap_context;

void __attribute__((naked, aligned(4))) trap_entry(void) {
  __asm__ volatile(
      ".option push\n"
      ".option norelax\n"
      "csrr t0, mcause\n"
      "la t1, trap_mcause\n"
      "sd t0, 0(t1)\n"
      "csrr t0, mepc\n"
      "la t1, trap_mepc\n"
      "sd t0, 0(t1)\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "csrr t0, mtval\n"
      "la t1, trap_mtval\n"
      "sd t0, 0(t1)\n"
      "csrr t0, 0x081\n"
      "la t1, trap_context\n"
      "sd t0, 0(t1)\n"
      "li t0, 1\n"
      "la t1, trap_seen\n"
      "sd t0, 0(t1)\n"
      ".option pop\n"
      "mret\n");
}

int main(void) {
  uintptr_t handler = (uintptr_t)trap_entry;
  __asm__ volatile("csrw mtvec, %0" : : "r"(handler) : "memory");
  __asm__ volatile("ecall" : : : "memory");

  bp_print_string("=== Synchronous Trap CSR Bank Test ===\n");
  bp_print_string("trap_seen:    ");
  bp_hprint_uint64(trap_seen);
  bp_print_string("\nmcause:       ");
  bp_hprint_uint64(trap_mcause);
  bp_print_string("\nmepc:         ");
  bp_hprint_uint64(trap_mepc);
  bp_print_string("\nmtval:        ");
  bp_hprint_uint64(trap_mtval);
  bp_print_string("\ncontext:      ");
  bp_hprint_uint64(trap_context);
  bp_print_string("\n");

  if ((trap_seen == 1) && (trap_mcause == 11) && (trap_mtval == 0)
      && (trap_context == 0)) {
    bp_print_string("[BSG-PASS] synchronous trap CSR bank verified\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] synchronous trap CSR bank mismatch\n");
    bp_finish(1);
  }

  return 0;
}
