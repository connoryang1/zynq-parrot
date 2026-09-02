/*
 * Reproduce the Linux kernel's first S-mode instructions after OpenSBI
 * hands off at 0x80200000.  Linux has not enabled translation at this point,
 * so this intentionally uses physical DRAM addresses and isolates the early
 * privilege/atomic/high-DRAM path from subsequent Linux setup.
 */

#include <stdint.h>
#include "bp_utils.h"

#define MSTATUS_MPP_MASK (3ULL << 11)
#define MSTATUS_MPP_S    (1ULL << 11)

#define LINUX_LOTTERY_ADDR  0x818eb330ULL
#define LINUX_BSS_BEGIN     0x818ec000ULL
#define LINUX_BSS_PROBE_BYTES 4096ULL
#define LINUX_STACK_TOP      0x81803ee0ULL

static volatile uint64_t trap_mcause;

/* Linux's next call after clearing its early BSS lands at 0x80c05544. */
int __attribute__((naked, noinline, section(".linux_high_text"))) linux_high_text_probe(void)
{
  __asm__ volatile(
      "addi sp, sp, -96\n\t"
      "sd ra, 88(sp)\n\t"
      "li a0, 0x5a\n\t"
      "ld ra, 88(sp)\n\t"
      "addi sp, sp, 96\n\t"
      "ret\n\t");
}

static inline uint32_t amoadd_w(volatile uint32_t *address, uint32_t value)
{
  uint32_t old;
  __asm__ volatile("amoadd.w %0, %2, (%1)"
                   : "=r"(old)
                   : "r"(address), "r"(value)
                   : "memory");
  return old;
}

void __attribute__((noinline, noreturn)) machine_recovery(void)
{
  bp_print_string("[BSG-FAIL] Linux-entry analogue trapped; mcause=");
  bp_hprint_uint64(trap_mcause);
  bp_print_string("\n");
  bp_finish(1);
  while (1) { }
}

void __attribute__((naked, aligned(4))) machine_trap_entry(void)
{
  __asm__ volatile(
      "csrr t0, mcause\n\t"
      "la t1, trap_mcause\n\t"
      "sd t0, 0(t1)\n\t"
      "csrr t0, mstatus\n\t"
      "li t1, 0x1800\n\t"
      "or t0, t0, t1\n\t"
      "csrw mstatus, t0\n\t"
      "la t0, machine_recovery\n\t"
      "csrw mepc, t0\n\t"
      "mret\n\t");
}

void __attribute__((noinline, noreturn)) supervisor_entry(void)
{
  volatile uint32_t *const lottery = (volatile uint32_t *)LINUX_LOTTERY_ADDR;
  volatile uint64_t *const bss = (volatile uint64_t *)LINUX_BSS_BEGIN;
  uint32_t old;
  uintptr_t address;

  bp_print_string("[STAGE] S-mode entered\n");
  /* These are the first two CSR writes in Linux's S-mode entry stub. */
  __asm__ volatile("csrw sie, zero" : : : "memory");
  bp_print_string("[STAGE] SIE cleared\n");
  __asm__ volatile("csrw sip, zero" : : : "memory");
  bp_print_string("[STAGE] SIP cleared\n");

  /* The host-model DRAM allocator is intentionally uninitialized.  Linux
   * starts after the board runner has cleared DRAM, so establish that same
   * lottery precondition here before checking the atomic return value. */
  *lottery = 0;
  old = amoadd_w(lottery, 1);
  bp_print_string("[STAGE] high-DRAM AMOADD old=");
  bp_hprint_uint64(old);
  bp_print_string("\n");

  /* Exercise the high-DRAM zeroing path without making this fast local gate
   * spend seconds emulating Linux's entire early BSS sweep. */
  for (address = LINUX_BSS_BEGIN;
       address < LINUX_BSS_BEGIN + LINUX_BSS_PROBE_BYTES;
       address += sizeof(uint64_t))
    *(volatile uint64_t *)address = 0;

  bp_print_string("[STAGE] high-text/high-stack fetch\n");
  __asm__ volatile("mv sp, %0" : : "r"(LINUX_STACK_TOP) : "memory");
  if ((old == 0) && (*lottery == 1) && (linux_high_text_probe() == 0x5a)) {
    bp_print_string("[BSG-PASS] Linux-entry CSR/AMO/BSS sequence completed\n");
    bp_finish(0);
  } else {
    bp_print_string("[BSG-FAIL] Linux-entry AMO result mismatch\n");
    bp_finish(1);
  }
  while (1) { }
}

int main(void)
{
  uint64_t status;

  /* The board runner zeroes DRAM before loading the NBF, just as Linux expects. */
  bp_print_string("[STAGE] M-mode setup\n");

  __asm__ volatile("csrw mtvec, %0" : : "r"((uintptr_t)machine_trap_entry) : "memory");
  __asm__ volatile("csrw mepc, %0" : : "r"((uintptr_t)supervisor_entry) : "memory");
  __asm__ volatile("csrr %0, mstatus" : "=r"(status));
  status = (status & ~MSTATUS_MPP_MASK) | MSTATUS_MPP_S;
  __asm__ volatile("csrw mstatus, %0" : : "r"(status) : "memory");
  __asm__ volatile("mret" : : : "memory");
  __builtin_unreachable();
}
