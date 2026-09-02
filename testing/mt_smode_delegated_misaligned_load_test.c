/*
 * Verify the exact supervisor-mode exception route Linux uses when its
 * unaligned-copy benchmark executes a word load on an unaligned address:
 * medeleg(load-address-misaligned) -> stvec -> sret.
 *
 * This is deliberately a recovery test, not a hardware-misaligned-access
 * performance test.  The handler skips the known four-byte LD after recording
 * architectural trap state, proving forward progress through the delegated
 * path without depending on an undefined destination register.
 */

#include <stdint.h>
#include "bp_utils.h"

#define LOAD_ADDR_MISALIGNED 4ULL
#define MSTATUS_MPP_MASK     (3ULL << 11)
#define MSTATUS_MPP_S        (1ULL << 11)

typedef struct {
  uint64_t scause;
  uint64_t sepc;
  uint64_t stval;
  uint64_t seen;
} trap_record_s;

static uint64_t source_words[2] __attribute__((aligned(16), used)) = {
  0x1122334455667788ULL,
  0x99aabbccddeeff00ULL,
};
static volatile trap_record_s trap_record;

static inline void emit_marker(char c) {
  *(volatile uint8_t *)0x00101000UL = (uint8_t)c;
}

/*
 * The Zynq host initially halts BlackParrot through its debug IRQ.  Normal
 * execution reaches M mode through the boot ROM, which programs dcsr/dpc and
 * executes dret.  This focused NBF bypasses that ROM, so reproduce only that
 * architectural handoff before testing supervisor exception delegation.
 */
static inline void leave_debug_to_machine(void) {
  __asm__ volatile(
      "li t0, 3\n"
      "csrw dcsr, t0\n"
      "la t0, 1f\n"
      "csrw dpc, t0\n"
      "dret\n"
      "1:\n"
      : : : "t0", "memory");
}

void __attribute__((naked, aligned(4))) supervisor_trap_entry(void) {
  __asm__ volatile(
      "li t3, 0x00101000\n"
      "li t1, 'T'\n"
      "sb t1, 0(t3)\n"
      "la t0, trap_record\n"
      "csrr t1, scause\n"
      "andi t2, t1, 0xf\n"
      "addi t2, t2, '0'\n"
      "sb t2, 0(t3)\n"
      "li t2, 'C'\n"
      "sb t2, 0(t3)\n"
      "sd t1, 0(t0)\n"
      "li t2, 'D'\n"
      "sb t2, 0(t3)\n"
      "csrr t1, sepc\n"
      "andi t2, t1, 0xf\n"
      "addi t2, t2, '0'\n"
      "sb t2, 0(t3)\n"
      "li t2, 'E'\n"
      "sb t2, 0(t3)\n"
      "sd t1, 8(t0)\n"
      "li t2, 'F'\n"
      "sb t2, 0(t3)\n"
      "addi t1, t1, 4\n"
      "csrw sepc, t1\n"
      "li t2, 'G'\n"
      "sb t2, 0(t3)\n"
      "csrr t1, stval\n"
      "li t2, 'H'\n"
      "sb t2, 0(t3)\n"
      "sd t1, 16(t0)\n"
      "li t2, 'I'\n"
      "sb t2, 0(t3)\n"
      "li t1, 1\n"
      "sd t1, 24(t0)\n"
      "li t2, 'J'\n"
      "sb t2, 0(t3)\n"
      "li t2, 'K'\n"
      "sb t2, 0(t3)\n"
      "sret\n");
}

void __attribute__((noinline, noreturn)) supervisor_entry(void) {
  uintptr_t address = (uintptr_t)source_words + 1;
  uintptr_t fault_pc;
  uintptr_t ignored_load_value;

  emit_marker('S');
  emit_marker('U');

  __asm__ volatile(
      "la %0, 1f\n"
      ".option push\n"
      ".option norvc\n"
      "1: ld %1, 0(%2)\n"
      ".option pop\n"
      : "=r"(fault_pc), "=r"(ignored_load_value) : "r"(address) : "memory");

  emit_marker('R');

  bp_print_string("=== Delegated S-mode Misaligned Load Test ===\nseen:         ");
  bp_hprint_uint64(trap_record.seen);
  bp_print_string("\nscause:       ");
  bp_hprint_uint64(trap_record.scause);
  bp_print_string("\nsepc:         ");
  bp_hprint_uint64(trap_record.sepc);
  bp_print_string("\nstval:        ");
  bp_hprint_uint64(trap_record.stval);
  bp_print_string("\nexpected sepc:");
  bp_hprint_uint64(fault_pc);
  bp_print_string("\n");

  if (trap_record.seen == 1
      && trap_record.scause == LOAD_ADDR_MISALIGNED
      && trap_record.sepc == fault_pc
      && trap_record.stval == address) {
    bp_print_string("[BSG-PASS] delegated S-mode misaligned load recovered\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] delegated S-mode misaligned load mismatch\n");
    bp_finish(1);
  }
  while (1) { }
}

int main(void) {
  uint64_t status;
  uint64_t delegation = 1ULL << LOAD_ADDR_MISALIGNED;

  leave_debug_to_machine();
  __asm__ volatile("csrw stvec, %0" : : "r"((uint64_t)supervisor_trap_entry) : "memory");
  __asm__ volatile("csrs medeleg, %0" : : "r"(delegation) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"((uint64_t)supervisor_entry) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  emit_marker('M');
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
